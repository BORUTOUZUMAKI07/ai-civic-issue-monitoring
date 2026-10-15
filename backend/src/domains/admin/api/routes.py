import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.domains.issues.services.issue_service import IssueService
from src.domains.users.deps import get_current_active_user
from src.domains.users.models.user import User
from src.domains.users.rbac import require_admin
from src.domains.users.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


class ReviewAction(BaseModel):
    action: str  # "approve" | "reject" | "change_type"
    new_type: str | None = None  # only used when action="change_type"


def _review_queue_item(issue) -> dict:
    return {
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


def _user_item(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
    }


@router.get("/review-queue")
async def review_queue(
    # See issues.routes.list_issues — pagination bounds belong at the edge,
    # where the value arrives from the client.
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    require_admin(user)
    issues, total = await IssueService(db).list_review_queue(skip=skip, limit=limit)
    return {"items": [_review_queue_item(issue) for issue in issues], "total": total}


@router.get("/users")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str = "",
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    require_admin(user)
    users, total = await UserService(db).list_users(skip=skip, limit=limit, search=search, role=role)
    return {"items": [_user_item(u) for u in users], "total": total}


@router.post("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    body: ReviewAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    require_admin(user)
    target = await UserService(db).change_role(user, user_id, body.new_type or "")
    return {
        "detail": f"Role updated to {target.role.value}.",
        "user_id": target.id,
        "email": target.email,
        "role": target.role.value,
    }


@router.post("/review/{issue_id}")
async def review_issue(
    issue_id: int,
    body: ReviewAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    require_admin(user)
    issue = await IssueService(db).review_issue(issue_id, body.action, body.new_type)

    if issue is None:
        # A rejected issue is deleted, so the cached dashboard counts are stale.
        from src.domains.dashboard.api.routes import invalidate_dashboard_cache

        await invalidate_dashboard_cache()
        return {"detail": "Issue rejected and deleted.", "issue_id": issue_id}

    try:
        from src.domains.notifications.api.routes import broadcast_issue_update

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
    except Exception:  # best-effort audit emit, non-fatal  # nosec B110
        pass

    return {
        "detail": f"Issue {body.action}d successfully.",
        "issue_id": issue.id,
        "issue_type": issue.issue_type.value,
        "review_required": False,
    }


@router.get("/rejected-uploads")
async def rejected_uploads(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_active_user),
):
    """View rejected uploads for potential retraining data."""
    require_admin(user)

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
