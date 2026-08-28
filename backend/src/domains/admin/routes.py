import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.deps import get_current_active_user
from src.errors import ForbiddenError, NotFoundError
from src.models.issue import ISSUE_TYPE_MAP, Issue
from src.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


class ReviewAction(BaseModel):
    action: str  # "approve" | "reject" | "change_type"
    new_type: str | None = None  # only used when action="change_type"


def _require_admin(user: User) -> None:
    if user.role not in (UserRole.admin, UserRole.super_admin):
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


@router.get("/users")
async def list_users(
    skip: int = 0,
    limit: int = 50,
    search: str = "",
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    _require_admin(user)

    stmt = select(User)
    count_stmt = select(func.count(User.id))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(User.email.ilike(pattern) | User.full_name.ilike(pattern))
        count_stmt = count_stmt.where(User.email.ilike(pattern) | User.full_name.ilike(pattern))
    if role:
        stmt = stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)
    stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    users = list(result.scalars().all())
    total = (await db.execute(count_stmt)).scalar_one()

    return {
        "items": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role.value,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
        "total": total,
    }


@router.post("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    body: ReviewAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    _require_admin(user)

    valid_roles = [r.value for r in UserRole]
    if body.new_type not in valid_roles:
        raise ForbiddenError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
    if user_id == user.id:
        raise ForbiddenError("Cannot change your own role.")

    target = await db.get(User, user_id)
    if not target:
        raise NotFoundError("User not found.")

    if target.role == UserRole.super_admin:
        raise ForbiddenError("Cannot change the super admin's role.")

    if body.new_type == "super_admin":
        raise ForbiddenError("Super admin can only be assigned directly in the database.")

    if body.new_type == "admin" and user.role != UserRole.super_admin:
        raise ForbiddenError("Only the super admin can promote to admin.")

    from src.models.engineer import Engineer
    from src.repositories.assignment_repository import AssignmentRepository
    from src.repositories.engineer_repository import EngineerRepository

    engineer_repo = EngineerRepository(db)
    new_role = UserRole(body.new_type)

    # A user holds ONE functional role at a time, so changing roles is a swap.
    # Keep the engineer profile (operational field-deployment record) in sync:
    #   - promote to engineer  -> auto-create a profile
    #   - leave engineer       -> auto-remove the profile
    profile = await engineer_repo.get_by_user_id(target.id)

    if new_role == UserRole.engineer:
        if profile is None:
            profile = Engineer(
                user_id=target.id,
                ward_id=1,
                specialization="general",
                max_workload=10,
            )
            db.add(profile)
    elif profile is not None:
        # An engineer with open work can't be pulled off mid-job.
        active = await AssignmentRepository(db).count_active_for_engineer(profile.id)
        if active:
            raise ForbiddenError(
                "This engineer still has active assignments. Resolve them before changing the role."
            )
        await db.delete(profile)

    target.role = new_role
    await db.commit()
    await db.refresh(target)

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
