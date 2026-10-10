"""Add idempotency_keys for deduplicated issue creation.

Revision ID: 009
Revises: 008
Create Date: 2026-10-10

Reporters on flaky mobile networks retry a failed ``POST /issues/upload``; the
retry used to create a second issue for one physical pothole. This table lets
the upload route recognise a replay (same user + key + request hash), return
the original response verbatim, and refuse a key reused for a *different*
request.

The unique ``(user_id, key)`` constraint is what makes "first writer wins"
atomic: two concurrent identical requests race on the INSERT, one wins, the
loser reads the winner's row and waits/returns rather than creating a duplicate.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("key", sa.String(length=128), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("in_progress", "succeeded", "failed", name="idempotencystatus"),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    sa.Enum(name="idempotencystatus").drop(op.get_bind(), checkfirst=True)
