from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.deps import get_current_active_user
from src.domains.dashboard.schemas import HeatmapPoint, StatsResponse
from src.domains.issues.service import IssueService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    svc = IssueService(db)
    stats = await svc.get_dashboard_stats()
    return StatsResponse(**stats)


@router.get("/heatmap", response_model=list[HeatmapPoint])
async def get_heatmap(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    svc = IssueService(db)
    points = await svc.get_heatmap_data()
    return [HeatmapPoint(**p) for p in points]
