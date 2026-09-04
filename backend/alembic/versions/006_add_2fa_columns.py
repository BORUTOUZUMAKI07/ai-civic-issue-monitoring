"""Add two-factor authentication columns to users table

Revision ID: 006
Revises: 005
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.String(), nullable=True))
    op.add_column("users", sa.Column("two_factor_enabled", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("recovery_codes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "recovery_codes")
    op.drop_column("users", "two_factor_enabled")
    op.drop_column("users", "totp_secret")
