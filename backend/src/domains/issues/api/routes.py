import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.gate import gate_decision
from src.domains.issues.models.issue import IssueStatus
from src.domains.issues.schemas import IssueListResponse, IssueResponse, IssueStatusUpdate
from src.domains.issues.services.issue_service import IssueService
from src.domains.users.deps import get_current_active_user
from src.domains.users.models.user import User
from src.domains.users.rbac import require_admin
from src.shared.errors import BadRequestError
from src.shared.uploads import read_upload_bounded

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/issues", tags=["Issues"])

UPLOAD_DIR = Path("uploads/issues")


def _classify_image(image_bytes: bytes) -> dict | None:
    """Run real MobileNetV2 inference on image bytes."""
    try:
        from io import BytesIO

        from PIL import Image

        from src.core.gate import CIVIC_LABELS
        from src.ml.inference.predict import predict_issue

        image = Image.open(BytesIO(image_bytes))
        result = predict_issue(image)

        raw_label = result["label"]
        is_civic = raw_label in CIVIC_LABELS
        is_non_civic = raw_label == "non_civic"
        civic_prob = result.get("probabilities", {}).get(raw_label, result["confidence"])

        return {
            "label": raw_label,
            "is_civic": is_civic,
            "is_non_civic": is_non_civic,
            "confidence": result["confidence"],
            "civic_prob": civic_prob,
            "model": result.get("model", "mobilenet_v2"),
            "probabilities": result.get("probabilities", {}),
        }
    except Exception as e:
        logger.warning("Image classification failed, falling back to keyword: %s", e)
        return None


async def _log_rejected_upload(
    image_url: str,
    reporter_id: int,
    vision: dict | None,
    description: str,
    reason: str,
) -> None:
    """Persist rejected photo to MongoDB for future retraining."""
    try:
        from src.core.mongodb import mongodb_initialized

        if not mongodb_initialized:
            return
        from src.documents.rejected_upload import RejectedUploadDocument

        doc = RejectedUploadDocument(
            image_url=image_url,
            reporter_id=reporter_id,
            vision_label=vision["label"] if vision else "unknown",
            vision_confidence=vision["confidence"] if vision else 0.0,
            description=description,
            action_taken="rejected",
        )
        await doc.insert()
    except Exception as e:
        logger.warning("Failed to log rejected upload: %s", e)


async def _generate_embedding_async(text: str) -> Optional[str]:
    """Generate embedding, returning None on failure or unsupported provider."""
    try:
        from src.core.embeddings import generate_embedding

        vector = await generate_embedding(text)
        if vector is None:
            return None
        return json.dumps(vector)
    except Exception:
        return None


async def _build_rag_context(description: str) -> str:
    """Retrieve similar past issues and render them for the classifier prompt.

    Best-effort: any failure (unreachable DB, no embedder, no issues) returns an
    empty string so classification proceeds exactly as it would without RAG.
    """
    try:
        from src.core.database import AsyncSessionLocal
        from src.rag.context import build_rag_context
        from src.rag.retrieval import find_similar_issues

        async with AsyncSessionLocal() as session:
            similar = await find_similar_issues(session, description)
        return build_rag_context({"description": description}, similar)
    except Exception as e:
        logger.warning("RAG context build failed, classifying without it: %s", e)
        return ""


async def _run_agent_pipeline(
    issue_id: int,
    description: str,
    category: str,
    ward_id: str,
    category_confidence: float = 1.0,
) -> dict:
    """Run the LangGraph agent pipeline and return results."""
    try:
        from src.agents.graph import AnalyticsGraph

        # Retrieval context is only built when the feature is enabled, so the
        # default upload path opens no extra DB session and pays no latency.
        rag_context = ""
        if settings.RAG_CLASSIFY_ENABLED and description:
            rag_context = await _build_rag_context(description)

        graph = AnalyticsGraph()
        result = await graph.run(
            {
                "issue_id": str(issue_id),
                "description": description,
                "category": category,
                "ward_id": ward_id,
                "category_confidence": category_confidence,
                "rag_context": rag_context,
            }
        )
        # `result.get` is untyped; wrap so the declared `dict` return is honest
        # rather than laundering `Any` through a `-> dict` signature.
        return dict(result.get("result") or {})
    except Exception as e:
        return {"error": str(e)}


@router.post("/upload", response_model=IssueResponse)
async def upload_issue(
    file: UploadFile = File(...),
    # Typed and bounded by FastAPI, not parsed by hand: the old
    # ``latitude: str`` + ``float(latitude)`` turned a non-numeric or
    # out-of-range coordinate into an unhandled ``ValueError`` (500) and let
    # ``nan``/``inf`` through to the database. This is a 422 with the offending
    # field named, for every bad value, before the body is touched.
    latitude: float = Form(..., ge=-90, le=90),
    longitude: float = Form(..., ge=-180, le=180),
    description: str = Form("", max_length=2000),
    force_submit: str = Form("false"),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    force = force_submit.lower() == "true"

    # Bounded read. The multipart parser has already spooled the file to a
    # temporary file by now (the Content-Length guard in middleware is what
    # stops that for honest clients), but ``await file.read()`` would pull the
    # *whole* spool into memory — a 1 GB "photo" from an authenticated user,
    # times concurrent requests, is a one-request OOM. This reads at most the
    # ceiling plus one byte and refuses anything past it.
    content = await read_upload_bounded(file)
    filename = file.filename or "image.jpg"

    if idempotency_key is not None:
        return await _idempotent_upload(
            db=db,
            user=user,
            key=idempotency_key,
            filename=filename,
            content=content,
            lat_val=latitude,
            lon_val=longitude,
            description=description,
            force=force,
        )

    return await _execute_upload(
        db=db,
        user=user,
        filename=filename,
        content=content,
        lat_val=latitude,
        lon_val=longitude,
        description=description,
        force=force,
    )


def _idempotency_in_progress() -> JSONResponse:
    """409 while the original request carrying this key is still running."""
    return JSONResponse(
        status_code=409,
        content={
            "detail": "A request with this Idempotency-Key is already in progress.",
            "error_code": "IDEMPOTENCY_IN_PROGRESS",
        },
        headers={"Retry-After": "1"},
    )


async def _idempotent_upload(
    *,
    db: AsyncSession,
    user: User,
    key: str,
    filename: str,
    content: bytes,
    lat_val: float,
    lon_val: float,
    description: str,
    force: bool,
) -> IssueResponse | JSONResponse:
    """Run the upload at most once per (user, key).

    Returns the stored response verbatim on a replay, 409 while the original is
    in flight, and 400 when the key is reused for a different request. On a
    genuine failure the record is marked ``failed`` so the client's retry
    proceeds; on success it is marked ``succeeded`` and the response is stored.
    """
    from src.domains.issues.idempotency import (
        MAX_KEY_LENGTH,
        get_record,
        hash_request,
        mark_failed,
        mark_succeeded,
        reclaim_failed,
        start_in_progress,
    )
    from src.domains.issues.models.idempotency import IdempotencyStatus

    key = key.strip()
    if not key or len(key) > MAX_KEY_LENGTH:
        raise BadRequestError(f"Idempotency-Key must be between 1 and {MAX_KEY_LENGTH} characters.")

    request_hash = hash_request(user.id, lat_val, lon_val, description, force, filename, content)

    record = await get_record(db, user.id, key)
    if record is not None:
        if record.request_sha256 != request_hash:
            raise BadRequestError("Idempotency-Key was already used for a different request.")
        if record.status == IdempotencyStatus.succeeded and record.response_body:
            return JSONResponse(
                content=json.loads(record.response_body),
                status_code=record.response_status or 200,
                headers={"Idempotency-Replayed": "true"},
            )
        if record.status == IdempotencyStatus.in_progress:
            return _idempotency_in_progress()
        # `failed` -> a retry may reclaim it; only one concurrent retry wins.
        if not await reclaim_failed(db, record):
            return _idempotency_in_progress()
    else:
        record = await start_in_progress(db, user.id, key, request_hash)
        if record is None:
            # Lost the insert race to a concurrent identical request.
            return _idempotency_in_progress()

    try:
        result = await _execute_upload(
            db=db,
            user=user,
            filename=filename,
            content=content,
            lat_val=lat_val,
            lon_val=lon_val,
            description=description,
            force=force,
        )
    except Exception:
        await mark_failed(db, record)
        raise

    await mark_succeeded(db, record, 200, result.model_dump(mode="json"))
    return result


async def _execute_upload(
    *,
    db: AsyncSession,
    user: User,
    filename: str,
    content: bytes,
    lat_val: float,
    lon_val: float,
    description: str,
    force: bool,
) -> IssueResponse:
    svc = IssueService(db)
    svc.validate_image(filename, content)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = filename.split(".")[-1]
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    filepath = UPLOAD_DIR / stored_name
    await asyncio.to_thread(filepath.write_bytes, content)
    image_url = f"/uploads/issues/{stored_name}"

    vision = await asyncio.to_thread(_classify_image, content)
    gate = gate_decision(vision, description, force)

    if gate["action"] == "reject":
        await _log_rejected_upload(image_url, user.id, vision, description, gate["reason"])
        raise BadRequestError(gate["reason"])

    classification = {
        "label": gate["issue_type"],
        "confidence": gate["confidence"],
        "model": (vision["model"] if vision else "keyword_fallback"),
        "probabilities": (vision.get("probabilities", {}) if vision else {}),
    }

    if gate["reason"]:
        sep = ". " if description else ""
        description = f"{description}{sep}{gate['reason']}" if description else gate["reason"]

    issue = await svc.create_issue(
        image_url=image_url,
        latitude=lat_val,
        longitude=lon_val,
        reporter_id=user.id,
        classification=classification,
        description=description,
    )

    if gate["review_required"] and gate["action"] == "accept":
        issue.review_required = True
        await svc.issue_repo.commit()

    if gate["reason"] and gate["action"] == "accept":
        await _log_rejected_upload(image_url, user.id, vision, description, "overridden_approved")

    embedding_task = asyncio.create_task(_generate_embedding_async(description or classification["label"]))
    agent_task = asyncio.create_task(
        _run_agent_pipeline(
            issue.id,
            description,
            classification["label"],
            str(issue.ward_id),
            float(classification["confidence"]),
        )
    )

    embedding_json, agent_result = await asyncio.gather(embedding_task, agent_task)

    if embedding_json:
        from sqlalchemy import text as sa_text

        await db.execute(
            sa_text("UPDATE issues SET embedding = :emb WHERE id = :id"),
            {"emb": embedding_json, "id": issue.id},
        )
        await db.commit()

    engineer = None
    if not gate["review_required"]:
        engineer = await svc.assign_engineer(issue)
    assigned_to = engineer.user_id if engineer else None

    engineer_name = None
    if assigned_to:
        engineer_name = await svc.get_engineer_name(assigned_to)

    try:
        from src.domains.notifications.api.routes import broadcast_issue_update

        await broadcast_issue_update(
            {
                "type": "issue_created",
                "payload": {
                    "id": issue.id,
                    "issue_type": issue.issue_type.value,
                    "latitude": issue.latitude,
                    "longitude": issue.longitude,
                    "severity": issue.severity,
                    "status": issue.status.value,
                    "review_required": gate["review_required"],
                    "agent_result": agent_result,
                },
            }
        )
    except Exception:  # best-effort agent event, non-fatal  # nosec B110
        pass

    from src.domains.dashboard.api.routes import invalidate_dashboard_cache

    await invalidate_dashboard_cache()

    assignment = {"user_id": assigned_to, "full_name": engineer_name} if assigned_to else None
    return IssueResponse.from_issue(issue, assignment)


@router.get("/similar/{issue_id}")
async def find_similar(
    issue_id: int,
    top_k: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """RAG endpoint: find issues similar to a given issue using vector similarity."""
    svc = IssueService(db)
    issue = await svc.get_issue(issue_id)

    query_text = issue.description or issue.issue_type.value

    from src.rag.retrieval import find_similar_issues

    similar = await find_similar_issues(db, query_text, top_k=top_k, exclude_issue_id=issue_id)

    from src.rag.context import build_rag_context

    context = build_rag_context(
        {
            "issue_type": issue.issue_type.value,
            "description": issue.description,
            "severity": issue.severity,
            "ward_id": issue.ward_id,
        },
        similar,
    )

    return {
        "issue_id": issue_id,
        "similar_issues": similar,
        "rag_context": context,
        "count": len(similar),
    }


@router.get("/search")
async def search_issues(
    q: str = Query(..., min_length=2),
    top_k: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """RAG endpoint: semantic search for issues using natural language query."""
    from src.rag.context import build_rag_context
    from src.rag.retrieval import find_similar_issues

    similar = await find_similar_issues(db, q, top_k=top_k)
    context = build_rag_context({"description": q}, similar)

    return {
        "query": q,
        "results": similar,
        "rag_context": context,
        "count": len(similar),
    }


@router.get("", response_model=IssueListResponse)
async def list_issues(
    # Bounded: an unbounded `limit` turned `?limit=100000000` into a full
    # table scan plus a response of that many rows — one request, one worker
    # pinned, one client out of memory. `skip` is floored so `?skip=-1` cannot
    # smuggle a negative OFFSET past the ORM.
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    # Server-side filter/sort so the list page pages over the whole table
    # instead of slicing whatever first page it happened to fetch. Values are
    # constrained here; the repository maps them straight onto columns.
    status: Optional[str] = Query(None),
    issue_type: Optional[str] = Query(None),
    severity: Optional[int] = Query(None, ge=1, le=5),
    ward_id: Optional[int] = Query(None, ge=1),
    search: str = Query("", max_length=200),
    sort: str = Query("created_at", pattern="^(created_at|severity|confidence|status)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    # Reject an unknown status rather than silently returning everything: a
    # typo in a filter should surface as a 400, not as an unfiltered page.
    if status is not None and status not in {s.value for s in IssueStatus}:
        raise BadRequestError(f"Invalid status '{status}'")

    svc = IssueService(db)
    issues, total = await svc.list_issues(
        skip=skip,
        limit=limit,
        status=status,
        issue_type=issue_type,
        severity=severity,
        ward_id=ward_id,
        search=search,
        sort=sort,
        order=order,
    )
    a_map = await svc.get_assignment_map([i.id for i in issues])
    items = [IssueResponse.from_issue(i, a_map.get(i.id)) for i in issues]
    return IssueListResponse(items=items, total=total)


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(
    issue_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    svc = IssueService(db)
    issue = await svc.get_issue(issue_id)
    a_map = await svc.get_assignment_map([issue.id])
    return IssueResponse.from_issue(issue, a_map.get(issue.id))


@router.post("/{issue_id}/assign", response_model=IssueResponse)
async def assign_issue(
    issue_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    require_admin(user)
    svc = IssueService(db)
    issue = await svc.get_issue(issue_id)
    engineer_id = body.get("engineer_id")
    if not engineer_id:
        raise BadRequestError("engineer_id is required.")
    await svc.assign_issue_to_engineer(issue, int(engineer_id))
    await db.refresh(issue)
    a_map = await svc.get_assignment_map([issue.id])
    return IssueResponse.from_issue(issue, a_map.get(issue.id))


@router.post("/{issue_id}/reassign", response_model=IssueResponse)
async def reassign_issue(
    issue_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    require_admin(user)
    svc = IssueService(db)
    issue = await svc.get_issue(issue_id)
    engineer_id = body.get("engineer_id")
    if not engineer_id:
        raise BadRequestError("engineer_id is required.")
    await svc.assign_issue_to_engineer(issue, int(engineer_id))
    await db.refresh(issue)
    a_map = await svc.get_assignment_map([issue.id])
    return IssueResponse.from_issue(issue, a_map.get(issue.id))


@router.patch("/{issue_id}/status", response_model=IssueResponse)
async def update_issue_status(
    issue_id: int,
    body: IssueStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    svc = IssueService(db)
    issue = await svc.update_status(issue_id, body.status)
    from src.domains.dashboard.api.routes import invalidate_dashboard_cache

    await invalidate_dashboard_cache()
    a_map = await svc.get_assignment_map([issue.id])
    return IssueResponse.from_issue(issue, a_map.get(issue.id))


@router.delete("/{issue_id}")
async def delete_issue(
    issue_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    require_admin(user)
    svc = IssueService(db)
    issue = await svc.get_issue(issue_id)

    await svc.delete_issue(issue)
    from src.domains.dashboard.api.routes import invalidate_dashboard_cache

    await invalidate_dashboard_cache()
    try:
        from src.domains.notifications.api.routes import broadcast_issue_update

        await broadcast_issue_update(
            {
                "type": "issue_deleted",
                "payload": {"id": issue_id},
            }
        )
    except Exception:  # best-effort delete event, non-fatal  # nosec B110
        pass
    return {"detail": "Issue deleted.", "issue_id": issue_id}


@router.get("/media/{file_path:path}")
async def serve_media(
    file_path: str,
    user: User = Depends(get_current_active_user),
):
    """Serve an uploaded image to an authenticated caller.

    This replaces the unauthenticated ``app.mount("/uploads", StaticFiles(...))``
    which exposed every issue photo and resolution after-photo to anyone on the
    internet for as long as the file existed: no login, no rate limit, and no
    way to revoke access short of deleting the file. Photos of civic problems
    are not public artefacts; they carry location, timestamps and often the
    person who reported the issue.

    Path traversal is rejected explicitly rather than relying on
    ``StaticFiles``' own normalisation, because this handler does its own
    resolution: the request path is decoded before it reaches us, so ``..`` is
    literally present in the segments and must be refused by comparison.
    """
    import mimetypes

    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".heic", ".heif"}

    raw = file_path.strip()
    if not raw or raw.startswith("/") or "\\" in raw or "\0" in raw:
        raise HTTPException(status_code=400, detail="Invalid path.")

    parts = [p for p in raw.split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts):
        raise HTTPException(status_code=400, detail="Invalid path.")

    # Confine to uploads/: resolve and verify containment rather than trusting
    # the join, so an unexpected symlink cannot walk out of the tree either.
    root = Path("uploads").resolve()
    target = (root / Path(*parts)).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Invalid path.")

    if target.suffix.lower() not in allowed_suffixes:
        raise HTTPException(status_code=404, detail="Not found.")

    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found.")

    # Content type is derived from the (allowlisted) extension, never from
    # client-supplied headers, so a crafted request cannot talk the browser
    # into treating the bytes as HTML or SVG: the two types that execute
    # script. Belt and braces below the allowlist.
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if media_type.startswith("text/") or media_type in {"image/svg+xml", "application/xhtml+xml"}:
        raise HTTPException(status_code=404, detail="Not found.")

    return FileResponse(target, media_type=media_type)
