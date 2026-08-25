from datetime import datetime, timezone
from typing import Optional

from beanie import Document
from pydantic import Field


class RejectedUploadDocument(Document):
    """Log of rejected/intentionally-submitted civic issue uploads.

    Every hard-rejected image AND every user-overridden rejection is stored here.
    These become labeled training data for future retraining.
    """

    image_url: str
    reporter_id: int
    vision_label: str
    vision_confidence: float
    text_label: Optional[str] = None
    text_confidence: Optional[float] = None
    description: str = ""
    action_taken: str  # "rejected" | "overridden_approved" | "overridden_rejected"
    human_label: Optional[str] = None  # admin's corrected label if reviewed
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "rejected_uploads"
