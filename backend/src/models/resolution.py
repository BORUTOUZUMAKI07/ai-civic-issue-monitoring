from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Resolution(Base):
    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    issue_id: Mapped[int] = mapped_column(
        Integer,
        # See Assignment.issue_id: a deleted issue must take its resolution,
        # which is what made `db.delete(issue)` 500 on every resolved issue.
        ForeignKey("issues.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    engineer_id: Mapped[int | None] = mapped_column(
        Integer,
        # See Assignment.engineer_id — attribution is dropped rather than the
        # resolution itself when the engineer's profile is removed.
        ForeignKey("engineers.id", ondelete="SET NULL"),
        nullable=True,
    )
    before_image_url: Mapped[str] = mapped_column(String, nullable=False)
    after_image_url: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    issue = relationship("Issue", back_populates="resolution")
    engineer = relationship("Engineer")
