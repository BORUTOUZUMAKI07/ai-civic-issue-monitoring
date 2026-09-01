"""Remove extra issue categories and purge demo seed data

Revision ID: 005
Revises: 004
Create Date: 2026-09-01

Reduces the allowed issue_type categories from 7 to the 3 the product uses
(pothole, garbage, debris) by dropping the waterlogging, broken_streetlight,
sewage and road_damage values from the issuetype enum, and removes all
[DEMO] issues, their assignments, and the demo engineer accounts created by
the (now removed) backend/scripts/seed_demo.py script.

Ordering matters: the extra enum values are only referenced by demo rows, so
they must be deleted before the enum values can be dropped.
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def _demo_engineer_emails(table: str) -> str:
    # Demo engineers share the civicpulse.test domain used by seed_demo.py.
    return f"SELECT id FROM {table} WHERE email LIKE 'demo_%@civicpulse.test'"


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Assignments referencing either demo issues or demo engineers.
    bind.exec_driver_sql(
        """
        DELETE FROM assignments
        WHERE issue_id IN (SELECT id FROM issues WHERE description LIKE '[DEMO]%')
           OR engineer_id IN (
                SELECT e.id
                FROM engineers e
                JOIN users u ON u.id = e.user_id
                WHERE u.email LIKE 'demo_%@civicpulse.test'
           )
        """
    )

    # 2. Demo issues (this also frees the extra enum values).
    bind.exec_driver_sql("DELETE FROM issues WHERE description LIKE '[DEMO]%'")

    # 3. Demo engineer profiles.
    bind.exec_driver_sql(
        """
        DELETE FROM engineers
        WHERE user_id IN (SELECT id FROM users WHERE email LIKE 'demo_%@civicpulse.test')
        """
    )

    # 4. Demo engineer user accounts.
    bind.exec_driver_sql("DELETE FROM users WHERE email LIKE 'demo_%@civicpulse.test'")

    # 5. Rebuild the issuetype enum with only the 3 supported categories.
    # asyncpg does not implement ALTER TYPE ... DROP VALUE, so recreate the
    # enum via rename + create + column recast (works on every driver).
    bind.exec_driver_sql("ALTER TYPE issuetype RENAME TO issuetype_old")
    bind.exec_driver_sql("CREATE TYPE issuetype AS ENUM ('pothole', 'garbage', 'debris')")
    bind.exec_driver_sql(
        "ALTER TABLE issues ALTER COLUMN issue_type TYPE issuetype "
        "USING issue_type::text::issuetype"
    )
    bind.exec_driver_sql("DROP TYPE issuetype_old")


def downgrade() -> None:
    bind = op.get_bind()
    # Restore the full enum. The demo data cleanup is not reverted here.
    bind.exec_driver_sql("ALTER TYPE issuetype RENAME TO issuetype_min")
    bind.exec_driver_sql(
        "CREATE TYPE issuetype AS ENUM "
        "('pothole', 'garbage', 'debris', 'waterlogging', 'broken_streetlight', "
        "'sewage', 'road_damage')"
    )
    bind.exec_driver_sql(
        "ALTER TABLE issues ALTER COLUMN issue_type TYPE issuetype "
        "USING issue_type::text::issuetype"
    )
    bind.exec_driver_sql("DROP TYPE issuetype_min")