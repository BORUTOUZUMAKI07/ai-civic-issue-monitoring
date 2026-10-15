import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.base import Base


class IdempotencyStatus(str, enum.Enum):
    in_progress = "in_progress"
    succeeded = "succeeded"
    failed = "failed"


class IdempotencyKey(Base):
    """Lifecycle record for one client-supplied ``Idempotency-Key``.

    Reporters retry a failed upload on flaky mobile networks. Without a key the
    retry creates a second issue for one physical pothole; with it, the replay
    returns the original response and no duplicate row.

    Scoped to ``(user_id, key)``: a key means "this user's logical request",
    not a global token. ``request_sha256`` detects the other half of the
    contract — a key reused for a *different* body is a client bug and is
    rejected rather than silently answered with the wrong stored response.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(
        Enum(IdempotencyStatus), default=IdempotencyStatus.in_progress, nullable=False
    )
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The stored response body, serialised JSON. Text rather than JSONB: it is
    # an opaque replay blob, never queried into, and Text keeps the model
    # portable across the SQLite the test suite runs on and the PG it deploys to.
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
