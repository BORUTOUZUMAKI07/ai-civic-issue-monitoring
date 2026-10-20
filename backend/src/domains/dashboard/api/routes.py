from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.redis import delete_cached, get_cached_or_compute
from src.domains.dashboard.schemas import HeatmapPoint, PublicStatsResponse, StatsResponse
from src.domains.engineers.models.engineer import Engineer
from src.domains.issues.models.issue import Issue, IssueStatus
from src.domains.issues.services.issue_service import IssueService
from src.domains.users.deps import get_current_active_user
from src.domains.wards.models.ward import Ward

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

STATS_CACHE_KEY = "dashboard:stats"
HEATMAP_CACHE_KEY = "dashboard:heatmap"
PUBLIC_STATS_CACHE_KEY = "dashboard:public-stats"
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


@router.get("/public-stats", response_model=PublicStatsResponse)
async def get_public_stats(db: AsyncSession = Depends(get_db)):
    """Unauthenticated, aggregate-only counters for the public landing page.

    Deliberately not behind ``get_current_active_user``: the marketing page has
    no session, and showing real community numbers beats inventing them. The
    payload carries only counts (no coordinates, identities or per-issue rows),
    so it is safe to expose. RBAC only guards writes, so a plain GET like this
    passes the middleware. Cached like the authed stats endpoint so a busy
    landing page cannot hammer Postgres.
    """

    async def _compute() -> dict:
        total = (await db.execute(select(func.count(Issue.id)))).scalar_one()
        resolved = (
            await db.execute(
                select(func.count(Issue.id)).where(Issue.status.in_([IssueStatus.resolved, IssueStatus.verified]))
            )
        ).scalar_one()
        wards = (await db.execute(select(func.count(Ward.id)))).scalar_one()
        engineers = (
            await db.execute(select(func.count(Engineer.id)).where(Engineer.is_available.is_(True)))
        ).scalar_one()
        avg_hours: float | None = (
            await db.execute(select(func.avg(Engineer.avg_resolution_hours)).where(Engineer.avg_resolution_hours > 0))
        ).scalar_one()
        return {
            "total_issues": total,
            "resolved_issues": resolved,
            "wards_covered": wards,
            "active_engineers": engineers,
            "avg_resolution_hours": round(float(avg_hours), 1) if avg_hours is not None else None,
        }

    stats = await get_cached_or_compute(PUBLIC_STATS_CACHE_KEY, CACHE_TTL, _compute)
    return PublicStatsResponse(**stats)


async def invalidate_dashboard_cache() -> None:
    await delete_cached(STATS_CACHE_KEY)
    await delete_cached(HEATMAP_CACHE_KEY)
    await delete_cached(PUBLIC_STATS_CACHE_KEY)
