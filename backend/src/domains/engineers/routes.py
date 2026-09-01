from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.deps import get_current_active_user
from src.domains.engineers.schemas import EngineerResponse
from src.domains.engineers.service import EngineerService
from src.errors import BadRequestError, ForbiddenError, NotFoundError
from src.models.engineer import Engineer
from src.models.user import User, UserRole

router = APIRouter(prefix="/engineers", tags=["Engineers"])


def _require_admin(user: User) -> None:
    if user.role not in (UserRole.admin, UserRole.super_admin):
        raise ForbiddenError("Admin access required.")


class EngineerCreate(BaseModel):
    user_id: int
    ward_id: int
    specialization: str = "general"
    max_workload: int = 10


@router.get("", response_model=list[EngineerResponse])
async def list_engineers(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    svc = EngineerService(db)
    engineers = await svc.list_engineers()
    return [
        EngineerResponse(
            id=e.id,
            user_id=e.user_id,
            ward_id=e.ward_id,
            specialization=e.specialization,
            current_workload=e.current_workload,
            max_workload=e.max_workload,
            is_available=e.is_available,
            avg_resolution_hours=e.avg_resolution_hours,
        )
        for e in engineers
    ]


@router.post("", response_model=EngineerResponse)
async def create_engineer(
    body: EngineerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    _require_admin(user)
    svc = EngineerService(db)

    existing = await svc.engineer_repo.get_by_user_id(body.user_id)
    if existing:
        raise BadRequestError("This user already has an engineer profile.")

    from src.repositories.user_repository import UserRepository

    user_repo = UserRepository(db)
    target_user = await user_repo.get(body.user_id)
    if not target_user:
        raise NotFoundError("User not found.")

    if target_user.role == UserRole.super_admin:
        raise BadRequestError("Cannot give the super admin an engineer profile.")

    # Explicit "make this person an engineer" action: swap their role in one step.
    target_user.role = UserRole.engineer
    await db.commit()

    engineer = Engineer(
        user_id=body.user_id,
        ward_id=body.ward_id,
        specialization=body.specialization,
        max_workload=body.max_workload,
    )
    created = await svc.engineer_repo.create(engineer)

    return EngineerResponse(
        id=created.id,
        user_id=created.user_id,
        ward_id=created.ward_id,
        specialization=created.specialization,
        current_workload=created.current_workload,
        max_workload=created.max_workload,
        is_available=created.is_available,
        avg_resolution_hours=created.avg_resolution_hours,
    )


@router.get("/me/assignments")
async def my_assignments(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    svc = EngineerService(db)
    engineer = await svc.engineer_repo.get_by_user_id(user.id)
    if not engineer:
        raise BadRequestError("You do not have an engineer profile.")

    from sqlalchemy import select as sa_select

    from src.models.assignment import Assignment
    from src.models.issue import Issue

    stmt = (
        sa_select(Assignment, Issue)
        .join(Issue, Assignment.issue_id == Issue.id)
        .where(Assignment.engineer_id == engineer.id)
        .order_by(Assignment.assigned_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "items": [
            {
                "assignment_id": a.id,
                "status": a.status.value,
                "assigned_at": a.assigned_at.isoformat(),
                "sla_deadline": a.sla_deadline.isoformat(),
                "issue_id": i.id,
                "issue_type": i.issue_type.value,
                "severity": i.severity,
                "issue_status": i.status.value,
                "latitude": i.latitude,
                "longitude": i.longitude,
                "description": i.description,
                "image_url": i.image_url,
                "ward_id": i.ward_id,
                "created_at": i.created_at.isoformat(),
            }
            for a, i in rows
        ],
        "total": len(rows),
    }
