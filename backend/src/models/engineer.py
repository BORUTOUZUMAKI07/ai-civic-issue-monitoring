from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Engineer(Base):
    __tablename__ = "engineers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    ward_id: Mapped[int] = mapped_column(Integer, ForeignKey("wards.id"), nullable=False)
    specialization: Mapped[str] = mapped_column(String, default="general")
    current_workload: Mapped[int] = mapped_column(Integer, default=0)
    max_workload: Mapped[int] = mapped_column(Integer, default=10)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    avg_resolution_hours: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="engineer_profile")
    ward = relationship("Ward", back_populates="engineers")
    assignments = relationship("Assignment", back_populates="engineer")
