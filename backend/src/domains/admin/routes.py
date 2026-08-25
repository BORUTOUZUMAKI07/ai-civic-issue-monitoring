import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.deps import get_current_active_user
from src.errors import ForbiddenError, NotFoundError
from src.models.issue import Issue, IssueStatus, IssueType, ISSUE_TYPE_MAP
from src.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


class ReviewAction(BaseModel):
    action: str  # "approve" | "reject" | "change_type"
    new_type: str | None = None  # only used when action="change_type"


def _require_admin(user: User) -> None:
    if user.role != UserRole.admin:
        raise ForbiddenError("Admin access required.")


@router.get("/review-queue")
async def review_queue(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    _require_admin(user)

    stmt = (
        select(Issue)
        .where(Issue.review_required == True)  # noqa: E712
        .order_by(Issue.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    issues = list(result.scalars().all())

    count_stmt = select(func.count(Issue.id)).where(Issue.review_required == True)  # noqa: E712
    total = (await db.execute(count_stmt)).scalar_one()

    return {
        "items": [
            {
                "id": issue.id,
                "issue_type": issue.issue_type.value,
                "confidence": issue.confidence,
                "severity": issue.severity,
                "status": issue.status.value,
                "latitude": issue.latitude,
                "longitude": issue.longitude,
                "description": issue.description,
                "image_url": issue.image_url,
                "review_required": issue.review_required,
                "ward_id": issue.ward_id,
                "reporter_id": issue.reporter_id,
                "created_at": issue.created_at.isoformat(),
                "model_used": issue.model_used,
                "probabilities": issue.probabilities,
            }
            for issue in issues
        ],
        "total": total,
    }


@router.post("/review/{issue_id}")
async def review_issue(
    issue_id: int,
    body: ReviewAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    _require_admin(user)

    stmt = select(Issue).where(Issue.id == issue_id)
    result = await db.execute(stmt)
    issue = result.scalar_one_or_none()
    if not issue:
        raise NotFoundError("Issue not found.")

    if body.action == "reject":
        await db.delete(issue)
        await db.commit()
        return {"detail": "Issue rejected and deleted.", "issue_id": issue_id}

    if body.action == "change_type":
        if not body.new_type or body.new_type not in ISSUE_TYPE_MAP:
            raise ForbiddenError(f"Invalid type. Must be one of: {', '.join(ISSUE_TYPE_MAP.keys())}")
        issue.issue_type = ISSUE_TYPE_MAP[body.new_type]

    issue.review_required = False
    await db.commit()
    await db.refresh(issue)

    try:
        from src.domains.notifications.routes import broadcast_issue_update

        await broadcast_issue_update(
            {
                "type": "issue_reviewed",
                "payload": {
                    "id": issue.id,
                    "issue_type": issue.issue_type.value,
                    "action": body.action,
                },
            }
        )
    except Exception:
        pass

    return {
        "detail": f"Issue {body.action}d successfully.",
        "issue_id": issue.id,
        "issue_type": issue.issue_type.value,
        "review_required": False,
    }


@router.get("/rejected-uploads")
async def rejected_uploads(
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(get_current_active_user),
):
    """View rejected uploads for potential retraining data."""
    _require_admin(user)

    from src.documents.rejected_upload import RejectedUploadDocument

    try:
        docs = await RejectedUploadDocument.find().skip(skip).limit(limit).to_list()
        total = await RejectedUploadDocument.find().count()
        return {
            "items": [
                {
                    "id": str(doc.id),
                    "image_url": doc.image_url,
                    "vision_label": doc.vision_label,
                    "vision_confidence": doc.vision_confidence,
                    "description": doc.description,
                    "action_taken": doc.action_taken,
                    "created_at": doc.created_at.isoformat(),
                }
                for doc in docs
            ],
            "total": total,
        }
    except Exception as e:
        logger.warning("Failed to fetch rejected uploads: %s", e)
        return {"items": [], "total": 0}
