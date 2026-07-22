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
