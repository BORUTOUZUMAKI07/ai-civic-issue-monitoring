from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class IssueResponse(BaseModel):
    issue_type: str
    confidence: float
    ward: str
    severity: int
    status: str = "Open"
    review_required: bool = False
    message: str = ""
    assigned_to: str = "Unassigned"
    engineer_name: Optional[str] = "General Engineer"
    engineer_email: Optional[str] = "maintenance@vmc.gov.in"
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"
