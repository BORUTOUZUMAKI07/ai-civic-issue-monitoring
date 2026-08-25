from pydantic import BaseModel, field_validator

from src.models.issue import IssueStatus


class IssueCreate(BaseModel):
    latitude: float
    longitude: float
    description: str = ""


class IssueResponse(BaseModel):
    id: int
    issue_type: str
    confidence: float
    severity: int
    status: str
    latitude: float
    longitude: float
    description: str | None = None
    image_url: str
    review_required: bool
    ward_id: int
    reporter_id: int
    created_at: str
    assigned_to: str | None = None
    engineer_name: str | None = None
    model_used: str | None = None
    probabilities: dict | None = None


class IssueListResponse(BaseModel):
    items: list[IssueResponse]
    total: int


class IssueStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = [s.value for s in IssueStatus]
        if v not in valid_statuses:
            raise ValueError(f"Invalid status '{v}'. Must be one of: {', '.join(valid_statuses)}")
        return v
