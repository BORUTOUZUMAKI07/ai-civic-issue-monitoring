from datetime import datetime, timezone
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field


class DriftMetrics(BaseModel):
    p_value: float
    is_drift: bool
    test: str


class DriftReportDocument(Document):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window_size: int
    confidence_drift: Optional[DriftMetrics] = None
    label_drift: Optional[DriftMetrics] = None
    predictions_sample: list[dict] = Field(default_factory=list)
    alert_sent: bool = False

    class Settings:
        name = "drift_reports"
