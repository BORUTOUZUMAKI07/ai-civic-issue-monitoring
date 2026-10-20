from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.domains.engineers.schemas import EngineerResponse
from src.domains.engineers.services.engineer_service import EngineerService
from src.domains.users.deps import get_current_active_user
from src.domains.users.models.user import User
from src.domains.users.rbac import require_admin

router = APIRouter(prefix="/engineers", tags=["Engineers"])


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
    engineers = await EngineerService(db).list_engineers()
    return [EngineerResponse.from_engineer(e) for e in engineers]


@router.get("/list")
async def list_engineers_paged(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    specialization: str | None = Query(None),
    ward_id: int | None = Query(None, ge=1),
    available: bool | None = Query(None),
    sort: str = Query("id", pattern="^(id|current_workload|max_workload|avg_resolution_hours)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """Paginated, filterable, sortable engineer roster.

    Kept separate from ``GET /engineers`` (a plain array) because that shape is
    still consumed by the map, assignment picker and dashboard, which want the
    whole roster in one shot. This endpoint backs the engineers *list* page,
    which pages over the table with server-side filter/sort.
    """
    engineers, total = await EngineerService(db).list_engineers_paged(
        skip=skip,
        limit=limit,
        specialization=specialization,
        ward_id=ward_id,
        available=available,
        sort=sort,
        order=order,
    )
    return {"items": [EngineerResponse.from_engineer(e) for e in engineers], "total": total}


@router.post("", response_model=EngineerResponse)
async def create_engineer(
    body: EngineerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    require_admin(user)
    created = await EngineerService(db).create_engineer(
        user_id=body.user_id,
        ward_id=body.ward_id,
        specialization=body.specialization,
        max_workload=body.max_workload,
    )
    return EngineerResponse.from_engineer(created)


@router.get("/me", response_model=EngineerResponse)
async def my_engineer_profile(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """The caller's own engineer profile.

    Lets the client decide whether the engineer-only `/resolution` flow is
    available without reading the whole engineers list (which may be
    admin-scoped). 404 conventionally signals "no profile".
    """
    engineer = await EngineerService(db).get_my_profile(user.id)
    return EngineerResponse.from_engineer(engineer)


@router.get("/me/assignments")
async def my_assignments(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    items = await EngineerService(db).list_my_assignments(user.id)
    return {"items": items, "total": len(items)}
