from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Resolution(Base):
    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    issue_id: Mapped[int] = mapped_column(Integer, ForeignKey("issues.id"), unique=True, nullable=False)
    engineer_id: Mapped[int] = mapped_column(Integer, ForeignKey("engineers.id"), nullable=False)
    before_image_url: Mapped[str] = mapped_column(String, nullable=False)
    after_image_url: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    issue = relationship("Issue", back_populates="resolution")
    engineer = relationship("Engineer")
