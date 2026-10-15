import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.base import Base


class AssignmentStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    in_progress = "in_progress"
    completed = "completed"


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    issue_id: Mapped[int] = mapped_column(
        Integer,
        # Deleting an issue must take its assignments with it. Without this the
        # only way to delete an issue was to remember to clear `assignments`
        # first, and forgetting produced a foreign-key violation → 500.
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
    )
    engineer_id: Mapped[int | None] = mapped_column(
        Integer,
        # Nullable so that demoting an engineer — which deletes their
        # `engineers` row — preserves the assignment record instead of either
        # failing on the FK or cascading the history away. `assignments` with
        # no surviving engineer keep their timestamps and SLA data; only the
        # attribution goes.
        ForeignKey("engineers.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[AssignmentStatus] = mapped_column(Enum(AssignmentStatus), default=AssignmentStatus.pending)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    issue = relationship("Issue", back_populates="assignments")
    engineer = relationship("Engineer", back_populates="assignments")
