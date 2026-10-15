from pydantic import BaseModel, field_validator

from src.domains.issues.models.issue import Issue, IssueStatus


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

    @classmethod
    def from_issue(cls, issue: Issue, assignment: dict | None = None) -> "IssueResponse":
        """Serialize ``issue``, optionally enriched with its latest assignment.

        ``assignment`` is a row from
        :meth:`AssignmentRepository.latest_by_issue_ids` — ``{"user_id", "full_name"}``.
        Assignee is rendered as a *string* to match the field's declared type.
        """
        assigned_to = str(assignment["user_id"]) if assignment else None
        return cls(
            id=issue.id,
            issue_type=issue.issue_type.value,
            confidence=issue.confidence,
            severity=issue.severity,
            status=issue.status.value,
            latitude=issue.latitude,
            longitude=issue.longitude,
            description=issue.description,
            image_url=issue.image_url,
            review_required=issue.review_required,
            ward_id=issue.ward_id,
            reporter_id=issue.reporter_id,
            created_at=issue.created_at.isoformat(),
            assigned_to=assigned_to,
            engineer_name=assignment["full_name"] if assignment else None,
            model_used=issue.model_used,
            probabilities=issue.probabilities,
        )


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
