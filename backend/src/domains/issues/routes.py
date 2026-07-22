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
from src.domains.issues.schemas import IssueListResponse, IssueResponse, IssueStatusUpdate
from src.domains.issues.service import IssueService
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/issues", tags=["Issues"])

UPLOAD_DIR = Path("uploads/issues")

_MODEL_TO_ISSUE_MAP = {
    "pothole": "pothole",
    "garbage": "garbage",
    "debris": "debris",
    "non_civic": "road_damage",
}


def _classify_description(description: str) -> dict:
    if not description:
        return {"label": "pothole", "confidence": 0.5}

    desc_lower = description.lower()
    best_label = "pothole"
    best_score = 0

    keyword_map = {
        "pothole": ["pothole", "road damage", "road crack", "broken road"],
        "garbage": ["garbage", "waste", "trash", "rubbish", "dump", "litter"],
        "broken_streetlight": ["streetlight", "street light", "lamp", "no light"],
        "waterlogging": ["waterlogging", "flood", "water", "drainage", "stagnant"],
        "debris": ["debris", "rubble", "construction waste"],
        "sewage": ["sewage", "sewer", "clogged drain", "blocked drain"],
        "road_damage": ["road damage", "road broken", "asphalt", "road repair"],
    }

    for label, keywords in keyword_map.items():
        score = sum(1 for kw in keywords if kw in desc_lower)
        if score > best_score:
            best_score = score
            best_label = label

    confidence = min(0.95, 0.6 + best_score * 0.1)
    return {"label": best_label, "confidence": confidence}


def _classify_image(image_bytes: bytes) -> dict:
    """Run real MobileNetV2 inference on image bytes."""
    try:
        from io import BytesIO

        from PIL import Image

        from src.ml.inference.predict import predict_issue

        image = Image.open(BytesIO(image_bytes))
        result = predict_issue(image)

        model_label = result["label"]
        issue_label = _MODEL_TO_ISSUE_MAP.get(model_label, model_label)

        return {
            "label": issue_label,
            "confidence": result["confidence"],
            "model": result.get("model", "mobilenet_v2"),
            "probabilities": result.get("probabilities", {}),
        }
    except Exception as e:
        logger.warning("Image classification failed, falling back to keyword: %s", e)
        return None


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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    lat_val = float(latitude)
    lon_val = float(longitude)

    content = await file.read()
    svc = IssueService(db)
    svc.validate_image(file.filename or "image.jpg", content)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = (file.filename or "image.jpg").split(".")[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = UPLOAD_DIR / filename
    await asyncio.to_thread(filepath.write_bytes, content)
    image_url = f"/uploads/issues/{filename}"

    classification = _classify_image(content)
    if classification is None:
        classification = _classify_description(description)
        classification["model"] = "keyword_fallback"
    else:
        if not description:
            description = f"Image uploaded - auto-classified as {classification['label']}"

    issue = await svc.create_issue(
        image_url=image_url,
        latitude=lat_val,
        longitude=lon_val,
        reporter_id=user.id,
        classification=classification,
        description=description,
    )

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

    engineer = await svc.assign_engineer(issue)
    assigned_to = engineer.user_id if engineer else None

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
                    "agent_result": agent_result,
                },
            }
        )
    except Exception:
        pass

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
        engineer_name=None,
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
    items = [
        IssueResponse(
            id=i.id,
            issue_type=i.issue_type.value,
            confidence=i.confidence,
            severity=i.severity,
            status=i.status.value,
            latitude=i.latitude,
            longitude=i.longitude,
            description=i.description,
            image_url=i.image_url,
            review_required=i.review_required,
            ward_id=i.ward_id,
            reporter_id=i.reporter_id,
            created_at=i.created_at.isoformat(),
        )
        for i in issues
    ]
    return IssueListResponse(items=items, total=total)


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(
    issue_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    svc = IssueService(db)
    issue = await svc.get_issue(issue_id)
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
    )


@router.patch("/{issue_id}/status", response_model=IssueResponse)
async def update_issue_status(
    issue_id: int,
    body: IssueStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    svc = IssueService(db)
    issue = await svc.update_status(issue_id, body.status)
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
    )
