from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.deps import get_current_active_user
from src.domains.engineers.schemas import EngineerResponse
from src.domains.engineers.service import EngineerService

router = APIRouter(prefix="/engineers", tags=["Engineers"])


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
