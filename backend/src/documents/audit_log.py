from datetime import datetime, timezone
from typing import Optional

from beanie import Document
from pydantic import Field


class AuditLogDocument(Document):
    action: str
    user_id: Optional[int] = None
    resource_type: str
    resource_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "audit_logs"
