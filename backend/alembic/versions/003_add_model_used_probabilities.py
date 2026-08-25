"""Add model_used and probabilities columns to issues

Revision ID: 003
Revises: 002
Create Date: 2025-03-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "issues",
        sa.Column("model_used", sa.String(), nullable=True),
    )
    op.add_column(
        "issues",
        sa.Column("probabilities", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("issues", "probabilities")
    op.drop_column("issues", "model_used")
