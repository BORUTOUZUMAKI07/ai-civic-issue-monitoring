import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.base import Base


class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    engineer = "engineer"
    field_worker = "field_worker"
    viewer = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.field_worker)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    totp_secret: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery_codes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    totp_last_counter: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    # OAuth identity. A user is bound to exactly one (provider, sub) pair; when
    # ``oauth_provider`` is set the account has NO usable password and password
    # login is refused outright (see ``verify_password_for_login``). ``oauth_sub``
    # is indexed and unique-per-provider so identity is established by the
    # provider's subject, never by an email address an attacker may control.
    oauth_provider: Mapped[str | None] = mapped_column(String, nullable=True, default=None, index=True)
    oauth_sub: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    # Exactly one super admin is a deployment invariant, not just an
    # application rule. The partial unique index makes a second super_admin
    # impossible even for a direct SQL write or a careless bootstrap rerun;
    # Postgres and SQLite both support partial indexes, so tests see the same
    # guarantee as production.
    __table_args__ = (
        Index(
            "uq_users_single_super_admin",
            "role",
            unique=True,
            postgresql_where=text("role = 'super_admin'"),
            sqlite_where=text("role = 'super_admin'"),
        ),
        Index(
            "uq_users_oauth_identity",
            "oauth_provider",
            "oauth_sub",
            unique=True,
        ),
    )

    issues = relationship("Issue", back_populates="reporter")
    engineer_profile = relationship("Engineer", back_populates="user", uselist=False)
