"""Add embedding vector column to issues

Revision ID: 002
Revises: 001
Create Date: 2025-02-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "issues",
        sa.Column("embedding", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("issues", "embedding")
