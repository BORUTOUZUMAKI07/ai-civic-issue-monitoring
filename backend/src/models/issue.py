import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class IssueType(str, enum.Enum):
    pothole = "pothole"
    garbage = "garbage"
    debris = "debris"


ISSUE_TYPE_MAP = {t.value: t for t in IssueType}


class IssueStatus(str, enum.Enum):
    reported = "reported"
    assigned = "assigned"
    in_progress = "in_progress"
    resolved = "resolved"
    verified = "verified"
    rejected = "rejected"


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    issue_type: Mapped[IssueType] = mapped_column(Enum(IssueType), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[IssueStatus] = mapped_column(Enum(IssueStatus), default=IssueStatus.reported)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str] = mapped_column(String, nullable=False)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    model_used: Mapped[str | None] = mapped_column(String, nullable=True)
    probabilities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)

    ward_id: Mapped[int] = mapped_column(Integer, ForeignKey("wards.id"), nullable=False)
    reporter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ward = relationship("Ward", back_populates="issues")
    reporter = relationship("User", back_populates="issues")
    assignments = relationship("Assignment", back_populates="issue")
    resolution = relationship("Resolution", back_populates="issue", uselist=False)
