import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.deps import get_current_active_user
from src.core.gate import gate_decision
from src.domains.issues.schemas import IssueListResponse, IssueResponse, IssueStatusUpdate
from src.domains.issues.service import IssueService
from src.errors import BadRequestError, ForbiddenError
from src.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/issues", tags=["Issues"])

UPLOAD_DIR = Path("uploads/issues")


def _require_admin(user: User) -> None:
    if user.role not in (UserRole.admin, UserRole.super_admin):
        raise ForbiddenError("Admin access required.")


async def _build_issue_response(svc: IssueService, issue, assignment_map: dict | None = None) -> IssueResponse:
    assigned_to = None
    engineer_name = None

    a = (assignment_map or {}).get(issue.id)
    if a:
        assigned_to = str(a["user_id"])
        engineer_name = a["full_name"]

    return IssueResponse(
        id=issue.id,
        issue_type=issue.issue_type.value,
        confidence=issue.confidence,
        severity=issue.severity,
        status=issue.status.value,
        latitude=issue.latitude,
        longitude=issue.longitude,
        description=issue.description,
        image_url=issue.image_url,
        review_required=issue.review_required,
        ward_id=issue.ward_id,
        reporter_id=issue.reporter_id,
        created_at=issue.created_at.isoformat(),
        assigned_to=assigned_to,
        engineer_name=engineer_name,
        model_used=issue.model_used,
        probabilities=issue.probabilities,
    )


async def _load_assignment_map(db, issue_ids: list[int]) -> dict:
    """Batch-load latest assignment+engineer+user for all issues in one query."""
    if not issue_ids:
        return {}
    from sqlalchemy import func
    from sqlalchemy import select as sa_select

    from src.models.assignment import Assignment
    from src.models.engineer import Engineer
    from src.models.user import User

    subq = (
        sa_select(
            Assignment.issue_id,
            func.max(Assignment.id).label("max_id"),
        )
        .where(Assignment.issue_id.in_(issue_ids))
        .group_by(Assignment.issue_id)
        .subquery()
    )

    stmt = (
        sa_select(Assignment, Engineer.user_id, User.full_name)
        .join(subq, Assignment.id == subq.c.max_id)
        .join(Engineer, Assignment.engineer_id == Engineer.id)
        .join(User, Engineer.user_id == User.id)
    )
    result = await db.execute(stmt)
    return {row[0].issue_id: {"user_id": row[1], "full_name": row[2]} for row in result.all()}


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


async def _run_agent_pipeline(issue_id: int, description: str, category: str, ward_id: str) -> dict:
    """Run the LangGraph agent pipeline and return results."""
    try:
        from src.agents.graph import AnalyticsGraph

        graph = AnalyticsGraph()
        result = await graph.run(
            {
                "issue_id": str(issue_id),
                "description": description,
                "category": category,
                "ward_id": ward_id,
            }
        )
        return result.get("result", {})
    except Exception as e:
        return {"error": str(e)}


@router.post("/upload", response_model=IssueResponse)
async def upload_issue(
    file: UploadFile = File(...),
    latitude: str = Form(...),
    longitude: str = Form(...),
    description: str = Form(""),
    force_submit: str = Form("false"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    lat_val = float(latitude)
    lon_val = float(longitude)
    force = force_submit.lower() == "true"

    content = await file.read()
    svc = IssueService(db)
    svc.validate_image(file.filename or "image.jpg", content)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = (file.filename or "image.jpg").split(".")[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = UPLOAD_DIR / filename
    await asyncio.to_thread(filepath.write_bytes, content)
    image_url = f"/uploads/issues/{filename}"

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
        _run_agent_pipeline(issue.id, description, classification["label"], str(issue.ward_id))
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
        from src.domains.notifications.routes import broadcast_issue_update

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
    except Exception:
        pass

    from src.domains.dashboard.routes import invalidate_dashboard_cache

    await invalidate_dashboard_cache()

    return IssueResponse(
        id=issue.id,
        issue_type=issue.issue_type.value,
        confidence=issue.confidence,
        severity=issue.severity,
        status=issue.status.value,
        latitude=issue.latitude,
        longitude=issue.longitude,
        description=issue.description,
        image_url=issue.image_url,
        review_required=issue.review_required,
        ward_id=issue.ward_id,
        reporter_id=issue.reporter_id,
        created_at=issue.created_at.isoformat(),
        assigned_to=str(assigned_to) if assigned_to else None,
        engineer_name=engineer_name,
        model_used=issue.model_used,
        probabilities=issue.probabilities,
    )


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
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    svc = IssueService(db)
    issues, total = await svc.list_issues(skip=skip, limit=limit)
    a_map = await _load_assignment_map(db, [i.id for i in issues])
    items = [_build_issue_response(svc, i, a_map) for i in issues]
    return IssueListResponse(items=await asyncio.gather(*items), total=total)


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(
    issue_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    svc = IssueService(db)
    issue = await svc.get_issue(issue_id)
    a_map = await _load_assignment_map(db, [issue.id])
    return await _build_issue_response(svc, issue, a_map)


@router.post("/{issue_id}/assign", response_model=IssueResponse)
async def assign_issue(
    issue_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    _require_admin(user)
    svc = IssueService(db)
    issue = await svc.get_issue(issue_id)
    engineer_id = body.get("engineer_id")
    if not engineer_id:
        raise BadRequestError("engineer_id is required.")
    await svc.assign_issue_to_engineer(issue, int(engineer_id))
    await db.refresh(issue)
    a_map = await _load_assignment_map(db, [issue.id])
    return await _build_issue_response(svc, issue, a_map)


@router.post("/{issue_id}/reassign", response_model=IssueResponse)
async def reassign_issue(
    issue_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    _require_admin(user)
    svc = IssueService(db)
    issue = await svc.get_issue(issue_id)
    engineer_id = body.get("engineer_id")
    if not engineer_id:
        raise BadRequestError("engineer_id is required.")
    await svc.assign_issue_to_engineer(issue, int(engineer_id))
    await db.refresh(issue)
    a_map = await _load_assignment_map(db, [issue.id])
    return await _build_issue_response(svc, issue, a_map)


@router.patch("/{issue_id}/status", response_model=IssueResponse)
async def update_issue_status(
    issue_id: int,
    body: IssueStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    svc = IssueService(db)
    issue = await svc.update_status(issue_id, body.status)
    from src.domains.dashboard.routes import invalidate_dashboard_cache

    await invalidate_dashboard_cache()
    a_map = await _load_assignment_map(db, [issue.id])
    return await _build_issue_response(svc, issue, a_map)


@router.delete("/{issue_id}")
async def delete_issue(
    issue_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    _require_admin(user)
    svc = IssueService(db)
    issue = await svc.get_issue(issue_id)

    from sqlalchemy import delete as sa_delete

    from src.models.assignment import Assignment

    await db.execute(sa_delete(Assignment).where(Assignment.issue_id == issue.id))

    await db.delete(issue)
    await db.commit()
    from src.domains.dashboard.routes import invalidate_dashboard_cache

    await invalidate_dashboard_cache()
    return {"detail": "Issue deleted.", "issue_id": issue_id}
