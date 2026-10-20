from pydantic import BaseModel


class StatsResponse(BaseModel):
    total_issues: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_ward: list[dict]
    recent_count: int


class HeatmapPoint(BaseModel):
    lat: float
    lng: float
    type: str
    severity: int
    status: str


class PublicStatsResponse(BaseModel):
    """Aggregate, non-sensitive counters safe to show on the public landing page.

    Deliberately *only* totals and coarse breakdowns -- no coordinates, no
    reporter identity, no per-issue rows. A landing page that wants to prove the
    platform is live can render these honestly instead of inventing numbers.
    """

    total_issues: int
    resolved_issues: int
    wards_covered: int
    active_engineers: int
    avg_resolution_hours: float | None = None
