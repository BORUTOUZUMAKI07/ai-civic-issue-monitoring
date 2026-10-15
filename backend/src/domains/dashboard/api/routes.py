from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.redis import delete_cached, get_cached_or_compute
from src.domains.dashboard.schemas import HeatmapPoint, StatsResponse
from src.domains.issues.services.issue_service import IssueService
from src.domains.users.deps import get_current_active_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

STATS_CACHE_KEY = "dashboard:stats"
HEATMAP_CACHE_KEY = "dashboard:heatmap"
CACHE_TTL = 30  # seconds


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    async def _compute() -> dict:
        return dict(await IssueService(db).get_dashboard_stats())

    # get_cached_or_compute collapses the post-invalidation stampede: every
    # client that refreshes the dashboard within the same instant shares one
    # database computation instead of each issuing its own.
    stats = await get_cached_or_compute(STATS_CACHE_KEY, CACHE_TTL, _compute)
    return StatsResponse(**stats)


@router.get("/heatmap", response_model=list[HeatmapPoint])
async def get_heatmap(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    async def _compute() -> list[dict]:
        return list(await IssueService(db).get_heatmap_data())

    points = await get_cached_or_compute(HEATMAP_CACHE_KEY, CACHE_TTL, _compute)
    return [HeatmapPoint(**p) for p in points]


async def invalidate_dashboard_cache() -> None:
    await delete_cached(STATS_CACHE_KEY)
    await delete_cached(HEATMAP_CACHE_KEY)
