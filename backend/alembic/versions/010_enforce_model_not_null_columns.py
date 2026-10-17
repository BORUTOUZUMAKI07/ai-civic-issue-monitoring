"""Give migration 001's defaulted columns the NOT NULL the models declare.

Revision ID: 010
Revises: 009
Create Date: 2026-10-17

Migration 001 created nineteen columns without ``nullable=False``. The models
type them non-Optional (``Mapped[T]``), which SQLAlchemy 2.0 renders as
``NOT NULL``, so the database has been looser than the model ever since and
``alembic check`` reported the same drift on every run.

Every one of these columns already carries a server-side default, so a row
written through the application always has a value; only a raw ``INSERT`` that
explicitly passed NULL could produce one. The upgrade therefore backfills any
such NULL to the column's own default *before* enforcing the constraint, so
``SET NOT NULL`` cannot fail on a long-lived production database.

Guarded by ``test_pg_integration.py::test_migrations_match_the_models``, which
runs ``alembic check`` against the freshly migrated container.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, literal used to backfill a NULL). Each literal mirrors the
# column's existing ``server_default`` in migration 001.
_NOT_NULL_DEFAULTS = [
    ("users", "role", "'field_worker'"),
    ("users", "is_active", "true"),
    ("users", "created_at", "now()"),
    ("users", "updated_at", "now()"),
    ("wards", "created_at", "now()"),
    ("engineers", "specialization", "'general'"),
    ("engineers", "current_workload", "0"),
    ("engineers", "max_workload", "10"),
    ("engineers", "is_available", "true"),
    ("engineers", "avg_resolution_hours", "0.0"),
    ("engineers", "created_at", "now()"),
    ("issues", "status", "'reported'"),
    ("issues", "review_required", "false"),
    ("issues", "created_at", "now()"),
    ("issues", "updated_at", "now()"),
    ("assignments", "status", "'pending'"),
    ("assignments", "assigned_at", "now()"),
    ("resolutions", "notes", "''"),
    ("resolutions", "resolved_at", "now()"),
]


def upgrade() -> None:
    for table, column, default in _NOT_NULL_DEFAULTS:
        op.execute(f"UPDATE {table} SET {column} = {default} WHERE {column} IS NULL")
        op.alter_column(table, column, nullable=False)


def downgrade() -> None:
    for table, column, _ in reversed(_NOT_NULL_DEFAULTS):
        op.alter_column(table, column, nullable=True)
