"""Give the issue/engineer foreign keys an explicit ON DELETE action.

Revision ID: 008
Revises: 007
Create Date: 2026-10-07

Every foreign key in the schema was created with a bare ``ForeignKey(...)``,
so PostgreSQL used the default ``NO ACTION``. That made two everyday operations
raise a foreign-key violation, which FastAPI turned into a 500:

* deleting or rejecting an issue that had ever been assigned or resolved
  (``assignments``/``resolutions`` still pointed at it);
* demoting an engineer who had ever resolved anything, which deletes their
  ``engineers`` row as part of the role change.

The application now clears dependents itself where it needs to (see
``IssueService.delete_issue``), so this migration is the database-level backstop
for anything that reaches around the service — and the reason the role change
no longer needs to care how much history an engineer has accumulated.
"""
from typing import TYPE_CHECKING, Union

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels = None
depends_on = None

# (table, column, ondelete, make_nullable)
_RULES = [
    ("assignments", "issue_id", "CASCADE", False),
    ("resolutions", "issue_id", "CASCADE", False),
    ("assignments", "engineer_id", "SET NULL", True),
    ("resolutions", "engineer_id", "SET NULL", True),
]


def _foreign_keys(bind: "Connection") -> dict[tuple[str, str], str]:
    """Map ``(table, column) -> constraint name`` for every FK in the schema.

    Read straight from ``pg_constraint`` rather than assuming the default
    ``<table>_<column>_fkey`` naming: the database may have been built by
    ``Base.metadata.create_all`` rather than by revision 001, and a wrong name
    here would fail mid-migration with no way back.
    """
    rows = bind.exec_driver_sql(
        """
        SELECT t.relname AS tbl,
               a.attname AS col,
               c.conname AS cname,
               pg_get_constraintdef(c.oid) AS cdef
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE c.contype = 'f'
        """
    ).fetchall()
    return {(tbl, col): cname for tbl, col, cname, _ in rows}


def _preflight(bind: "Connection") -> dict[tuple[str, str], str]:
    """Fail before any DDL if the schema is not what this revision expects.

    Silently skipping a missing constraint left the column widened but the FK
    unchanged — a half-migrated database that looked upgraded.
    """
    existing = _foreign_keys(bind)
    missing = [f"{table}.{column}" for table, column, *_ in _RULES if (table, column) not in existing]
    if missing:
        raise RuntimeError(
            "008: cannot alter foreign keys; missing constraints on "
            f"{', '.join(missing)}. Inspect the schema with \\d before upgrading."
        )
    return existing


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        # SQLite (the local/test engine) takes ON DELETE straight from the
        # model DDL, which has been updated to match — there is no constraint
        # to alter here.
        return

    bind = op.get_bind()
    existing = _preflight(bind)

    for table, column, ondelete, nullable in _RULES:
        if nullable:
            # Widen first: SET NULL is only legal if the column accepts NULL,
            # and the reverse order would fail on any table that still holds
            # a row attributed to an engineer being removed.
            op.alter_column(
                table,
                column,
                existing_type=sa.Integer(),
                existing_nullable=False,
                nullable=True,
                autoincrement=False,
            )
        name = existing[(table, column)]
        op.drop_constraint(name, table, type_="foreignkey")
        parent = "issues" if column == "issue_id" else "engineers"
        op.create_foreign_key(
            name,
            table,
            parent,
            [column],
            ["id"],
            ondelete=ondelete,
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    bind = op.get_bind()
    existing = _preflight(bind)

    # Restoring NOT NULL is only safe when no SET NULL has happened. Check
    # before any DDL: PostgreSQL rolls the whole migration back on error, so
    # an operator gets an actionable message instead of a half-downgraded DB.
    for table, column, _ondelete, nullable in _RULES:
        if not nullable:
            continue
        nulls = bind.exec_driver_sql(
            f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL'
        ).scalar()
        if nulls:
            raise RuntimeError(
                f"008 downgrade: {nulls} row(s) in {table}.{column} are NULL "
                "because an engineer was removed. Restore those assignments "
                "before reimposing NOT NULL."
            )

    for table, column, _ondelete, nullable in reversed(_RULES):
        name = existing[(table, column)]
        op.drop_constraint(name, table, type_="foreignkey")
        parent = "issues" if column == "issue_id" else "engineers"
        op.create_foreign_key(name, table, parent, [column], ["id"])
        if nullable:
            op.alter_column(table, column, existing_nullable=True, nullable=False, autoincrement=False)
