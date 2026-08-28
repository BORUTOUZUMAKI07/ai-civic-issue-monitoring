from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.deps import get_current_active_user
from src.core.redis import delete_cached, get_cached, set_cached
from src.domains.dashboard.schemas import HeatmapPoint, StatsResponse
from src.domains.issues.service import IssueService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

STATS_CACHE_KEY = "dashboard:stats"
HEATMAP_CACHE_KEY = "dashboard:heatmap"
CACHE_TTL = 30  # seconds


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    cached = await get_cached(STATS_CACHE_KEY)
    if cached:
        return StatsResponse(**cached)

    svc = IssueService(db)
    stats = await svc.get_dashboard_stats()
    await set_cached(STATS_CACHE_KEY, dict(stats), ttl=CACHE_TTL)
    return StatsResponse(**stats)


@router.get("/heatmap", response_model=list[HeatmapPoint])
async def get_heatmap(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    cached = await get_cached(HEATMAP_CACHE_KEY)
    if cached:
        return [HeatmapPoint(**p) for p in cached]

    svc = IssueService(db)
    points = await svc.get_heatmap_data()
    await set_cached(HEATMAP_CACHE_KEY, points, ttl=CACHE_TTL)
    return [HeatmapPoint(**p) for p in points]


async def invalidate_dashboard_cache() -> None:
    await delete_cached(STATS_CACHE_KEY)
    await delete_cached(HEATMAP_CACHE_KEY)
