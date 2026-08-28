"""Add super_admin to userrole enum

Revision ID: 004
Revises: 003
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'super_admin'")


def downgrade() -> None:
    pass
