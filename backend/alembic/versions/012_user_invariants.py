"""Enforce user-table invariants in the database.

Revision ID: 012
Revises: 011_auth_hardening_email_gdpr
Create Date: 2026-11-27

Adds two constraints the application alone cannot guarantee:

* ``uq_users_single_super_admin`` — a partial unique index on ``role`` for the
  ``super_admin`` row. There must be exactly one super admin; the API refuses to
  grant the role, but a bootstrap rerun or a direct SQL write could otherwise
  create a second one (or, by demoting, leave none).
* ``uq_users_oauth_identity`` — a unique index on ``(oauth_provider, oauth_sub)``
  so a provider subject can never be bound to two accounts. NULLs remain
  distinct in Postgres/SQLite, so password accounts are unaffected.

Both upgrades preflight the existing data and abort with an actionable message
rather than letting the database raise an opaque unique-violation error.
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: str | None = "011_auth_hardening_email_gdpr"
branch_labels: str | None = None
depends_on: str | None = None

logger = logging.getLogger("civicpulse")

_SUPER_ADMIN_INDEX = "uq_users_single_super_admin"
_OAUTH_IDENTITY_INDEX = "uq_users_oauth_identity"


def upgrade() -> None:
    bind = op.get_bind()

    super_admins = bind.execute(
        sa.text("SELECT id FROM users WHERE role = 'super_admin' ORDER BY id")
    ).scalars().all()
    if len(super_admins) > 1:
        raise RuntimeError(
            "012: refusing to add the single-super-admin constraint: "
            f"{len(super_admins)} rows have role='super_admin' "
            f"(ids: {', '.join(str(i) for i in super_admins)}). "
            "Demote all but the intended super admin before re-running Alembic."
        )

    # Empty strings used to be written by older OAuth code paths. Normalise them
    # to NULL so they behave like "no identity" instead of colliding as a shared
    # ("", "") pair under the new unique index.
    bind.execute(sa.text("UPDATE users SET oauth_provider = NULL WHERE oauth_provider = ''"))
    bind.execute(sa.text("UPDATE users SET oauth_sub = NULL WHERE oauth_sub = ''"))

    duplicates = bind.execute(
        sa.text(
            "SELECT oauth_provider, oauth_sub, COUNT(*) AS n "
            "FROM users WHERE oauth_provider IS NOT NULL AND oauth_sub IS NOT NULL "
            "GROUP BY oauth_provider, oauth_sub HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if duplicates:
        pairs = ", ".join(f"({p}, {s}) x{n}" for p, s, n in duplicates)
        raise RuntimeError(
            "012: refusing to add the OAuth identity constraint; duplicate "
            f"(provider, sub) pairs found: {pairs}. Resolve them before upgrading."
        )

    op.create_index(
        _SUPER_ADMIN_INDEX,
        "users",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'super_admin'"),
        sqlite_where=sa.text("role = 'super_admin'"),
    )
    op.create_index(
        _OAUTH_IDENTITY_INDEX,
        "users",
        ["oauth_provider", "oauth_sub"],
        unique=True,
    )
    logger.info("012: added single-super-admin and OAuth identity constraints")


def downgrade() -> None:
    op.drop_index(_OAUTH_IDENTITY_INDEX, table_name="users")
    op.drop_index(_SUPER_ADMIN_INDEX, table_name="users")
