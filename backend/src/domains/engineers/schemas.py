from pydantic import BaseModel


class EngineerResponse(BaseModel):
    id: int
    user_id: int
    ward_id: int
    specialization: str
    current_workload: int
    max_workload: int
    is_available: bool
    avg_resolution_hours: float
