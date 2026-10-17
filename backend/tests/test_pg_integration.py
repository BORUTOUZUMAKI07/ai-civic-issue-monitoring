"""
Real-Postgres integration tests (marker: ``integration``).
==========================================================

These tests need Docker. They are deliberately excluded from the default
``test-ci`` run (``-m 'not integration'``) and executed on their own by the
``test-integration`` pixi task and the ``backend-integration`` CI job.

Why a real database at all? The schema features that SQLite cannot express —
the ``JSONB`` columns, the ``issuetype`` enum, the ``ON DELETE`` rules
introduced by migrations 005/007/008, and the ``idempotency_keys`` table from
009 — are exactly the ones worth proving
against PostgreSQL. The suite never trusts that a migration chain "probably
applied"; it runs the real ``alembic upgrade head`` against a fresh
``postgres:16-alpine`` container and asserts on the catalog plus the runtime
behaviour. It also runs ``alembic check`` (``test_migrations_match_the_models``)
so a model that was never migrated — or a column migrated with the wrong
nullability, as migration 001 did — fails the build instead of drifting
unnoticed.

Whenever Docker is unavailable (no daemon, image pull failure), every test in
this module skips itself rather than failing — that keeps the gate honest on
machines without Docker without marking the module broken.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

BACKEND_DIR = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg():
    """A real Postgres container, or a graceful skip when Docker is unavailable.

    Only the missing-``testcontainers`` case is handled by conftest's
    session-scoped ``pg_container``; a stopped Docker daemon would fail hard
    there. This fixture catches the container-start failure itself so the whole
    module skips instead of erroring out.
    """
    pytest.importorskip("testcontainers", reason="pip install testcontainers to run integration tests")
    # `testcontainers.community.postgres` is the current home of the PG
    # container class; the top-level `testcontainers.postgres` path is
    # deprecated since 4.8 (conftest.py still uses it, but its fixtures are
    # not exercised by this module).
    from testcontainers.community.postgres import PostgresContainer

    try:
        with PostgresContainer("postgres:16-alpine") as container:
            yield container
    except Exception as exc:  # Docker daemon down, image pull failure, ...
        pytest.skip(f"Docker unavailable for integration tests: {exc}")


@pytest.fixture(scope="module")
def migrated_pg_url(pg) -> str:
    """URL of the container after the *real* migration chain has been applied.

    ``alembic upgrade head`` runs in its own interpreter (as production does),
    reading ``ASYNC_DATABASE_URI`` from the environment the same way the
    deployed migration step does — this is the exact command the backend runs
    against Aiven, just pointed at the throwaway container instead.
    """
    url = pg.get_connection_url()
    # get_connection_url() may hand back either `postgresql://` or (in newer
    # testcontainers) `postgresql+psycopg2://`; env.py's async engine needs
    # the asyncpg driver either way.
    for scheme in ("postgresql+psycopg2://", "postgresql://"):
        if url.startswith(scheme):
            url = "postgresql+asyncpg://" + url[len(scheme) :]
            break
    env = {
        **os.environ,
        # The conftest forces SQLite at import time of the *pytest* process;
        # the subprocess below re-imports settings fresh, so these two win.
        "ASYNC_DATABASE_URI": url,
        "DATABASE_URL": url,
    }
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"alembic upgrade head failed (rc={proc.returncode})\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return url


@pytest_asyncio.fixture(scope="module")
async def pg_engine(migrated_pg_url):
    """Asyncpg engine bound to the migrated container."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(migrated_pg_url, pool_size=1)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_db(pg_engine):
    """Isolate every test from the previous one's rows.

    With IDENTITY columns the fixture must delete first, then restart the
    sequences; ``CASCADE`` makes the order between the tables irrelevant.
    """
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE idempotency_keys, assignments, resolutions, issues, engineers, wards, users "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest_asyncio.fixture
async def conn(pg_engine):
    """One connection + transaction per test, rolled back on teardown."""
    async with pg_engine.connect() as connection:
        yield connection


# ─────────────────────────────────────────────────────────────────────────────
# Schema-level assertions (the catalog)
# ─────────────────────────────────────────────────────────────────────────────

async def test_alembic_reached_head(pg_engine) -> None:
    """The full chain 001→010 applied; the head revision is 010."""
    async with pg_engine.connect() as c:
        version = await c.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == "010"

    async with pg_engine.connect() as c:
        tables = {
            row[0]
            for row in await c.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public'"
                )
            )
        }
    assert {
        "users",
        "wards",
        "engineers",
        "issues",
        "assignments",
        "resolutions",
        "idempotency_keys",
    } <= tables


async def test_migrations_match_the_models(migrated_pg_url) -> None:
    """``alembic check`` must find nothing left to upgrade.

    The ``migrated_pg_url`` fixture has already applied the real chain to the
    container, so comparing the live schema with ``Base.metadata`` catches the
    two ways a change can go missing: a model edited without a migration, and a
    migration column created with the wrong nullability (both happened here —
    migration 001 left nineteen columns nullable that the models call NOT NULL,
    which is what migration 010 fixes). Without this, drift only shows up as a
    silent ``alembic check`` failure nobody runs.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=str(BACKEND_DIR),
        env={
            **os.environ,
            "ASYNC_DATABASE_URI": migrated_pg_url,
            "DATABASE_URL": migrated_pg_url,
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        "the models and the migration chain have drifted; add a migration (or "
        "reconcile the column) so the two agree\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


async def test_issue_type_enum_has_exactly_three_values(pg_engine) -> None:
    """Migration 005 pruned 7 categories down to the 3 the product uses."""
    async with pg_engine.connect() as c:
        labels = [
            row[0]
            for row in await c.execute(
                text(
                    "SELECT enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'issuetype' "
                    "ORDER BY e.enumsortorder"
                )
            )
        ]
    assert labels == ["pothole", "garbage", "debris"]


async def test_jsonb_columns_are_real_jsonb(pg_engine) -> None:
    """The JSON columns are stored as ``jsonb``, not text/varchar."""
    async with pg_engine.connect() as c:
        rows = await c.execute(
            text(
                "SELECT table_name, column_name, data_type "
                "FROM information_schema.columns "
                "WHERE (table_name = 'issues' AND column_name IN ('metadata', 'probabilities')) "
                "   OR (table_name = 'wards' AND column_name = 'polygon')"
            )
        )
        kinds = {(table, column): dtype for table, column, dtype in rows}
    assert kinds == {
        ("issues", "metadata"): "jsonb",
        ("issues", "probabilities"): "jsonb",
        ("wards", "polygon"): "jsonb",
    }


async def test_fk_on_delete_actions_match_migration_008(pg_engine) -> None:
    """issue_id FKs cascade; engineer_id FKs set NULL.

    ``confdeltype`` is what PostgreSQL itself recorded: ``c`` = CASCADE,
    ``n`` = SET NULL.
    """
    statement = text(
        """
        SELECT t.relname AS tbl, a.attname AS col,
               CASE c.confdeltype
                   WHEN 'c' THEN 'CASCADE'
                   WHEN 'n' THEN 'SET NULL'
                   ELSE 'NO ACTION'
               END AS fk_action
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE c.contype = 'f'
          AND t.relname IN ('assignments', 'resolutions')
        """
    )
    async with pg_engine.connect() as c:
        rows = await c.execute(statement)
        actions = {(tbl, col): action for tbl, col, action in rows}

    assert actions == {
        ("assignments", "issue_id"): "CASCADE",
        ("resolutions", "issue_id"): "CASCADE",
        ("assignments", "engineer_id"): "SET NULL",
        ("resolutions", "engineer_id"): "SET NULL",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Behavioural assertions (what the schema lets the app do)
# ─────────────────────────────────────────────────────────────────────────────

async def _seed_ward_user_engineer(conn) -> tuple[int, int]:
    """Insert one ward, one reporting user and one engineer; return (ward_id, engineer_id)."""
    ward_id = (
        await conn.execute(
            # asyncpg has no native dict binding — `type_=JSONB` makes SQLAlchemy
            # json-encode on the way in (and json-decode on the way out).
            text(
                "INSERT INTO wards (name, polygon, center_lat, center_lon) "
                "VALUES (:name, :polygon, :lat, :lon) RETURNING id"
            ).bindparams(bindparam("polygon", type_=JSONB)),
            {"name": "integration-ward", "polygon": {"type": "Feature", "props": {}}, "lat": 22.3, "lon": 73.2},
        )
    ).scalar_one()
    user_id = (
        await conn.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name) "
                "VALUES ('engineer@civicpulse.test', 'x', 'Eng') RETURNING id"
            )
        )
    ).scalar_one()
    engineer_id = (
        await conn.execute(
            text("INSERT INTO engineers (user_id, ward_id) VALUES (:u, :w) RETURNING id"),
            {"u": user_id, "w": ward_id},
        )
    ).scalar_one()
    return ward_id, engineer_id


async def _seed_issue(conn, ward_id: int, *, probabilities: dict | None = None) -> int:
    """Insert one pothole issue reported by a fresh user; return its id."""
    reporter_id = (
        await conn.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name) "
                "VALUES ('reporter@civicpulse.test', 'x', 'Rpt') RETURNING id"
            )
        )
    ).scalar_one()
    return (
        await conn.execute(
            text(
                "INSERT INTO issues "
                "(issue_type, confidence, severity, status, latitude, longitude, "
                " description, image_url, probabilities, \"metadata\", ward_id, reporter_id) "
                "VALUES ('pothole', :confidence, :severity, 'reported', :lat, :lon, "
                " :description, 'photo.png', :prob, :meta, :ward, :reporter) RETURNING id"
            ).bindparams(
                bindparam("prob", type_=JSONB),
                bindparam("meta", type_=JSONB),
            ),
            {
                "confidence": 0.98,
                "severity": 3,
                "lat": 22.31,
                "lon": 73.21,
                "description": "integration pothole",
                "prob": probabilities,
                "meta": {"source": "integration"},
                "ward": ward_id,
                "reporter": reporter_id,
            },
        )
    ).scalar_one()


async def _seed_assignment_and_resolution(conn, issue_id: int, engineer_id: int) -> None:
    # sla_deadline is NOT NULL with no server default, so it must be supplied.
    await conn.execute(
        text("INSERT INTO assignments (issue_id, engineer_id, sla_deadline) VALUES (:i, :e, now() + interval '1 day')"),
        {"i": issue_id, "e": engineer_id},
    )
    await conn.execute(
        text("INSERT INTO resolutions (issue_id, engineer_id, before_image_url, after_image_url) VALUES (:i, :e, 'a.png', 'b.png')"),
        {"i": issue_id, "e": engineer_id},
    )


async def test_jsonb_roundtrip(conn) -> None:
    """A dict stored in a JSONB column comes back byte-identical, and PG can query into it."""
    ward_id, _ = await _seed_ward_user_engineer(conn)
    probabilities = {"pothole": 0.91, "garbage": 0.05, "debris": 0.04}
    issue_id = await _seed_issue(conn, ward_id, probabilities=probabilities)

    row = (
        await conn.execute(
            text(
                "SELECT probabilities, \"metadata\", "
                "jsonb_typeof(probabilities) AS ptype, jsonb_typeof(\"metadata\") AS mtype, "
                "probabilities ->> 'pothole' AS pothole_prob "
                "FROM issues WHERE id = :id"
            ),
            {"id": issue_id},
        )
    ).one()
    assert row.probabilities == probabilities
    assert row.metadata == {"source": "integration"}
    assert (row.ptype, row.mtype) == ("object", "object")
    assert float(row.pothole_prob) == pytest.approx(0.91)


async def test_delete_issue_cascades_children(conn) -> None:
    """Deleting an issue removes its assignments and resolution at the DB level."""
    ward_id, engineer_id = await _seed_ward_user_engineer(conn)
    issue_id = await _seed_issue(conn, ward_id)
    await _seed_assignment_and_resolution(conn, issue_id, engineer_id)

    await conn.execute(text("DELETE FROM issues WHERE id = :id"), {"id": issue_id})

    remaining = (
        await conn.execute(
            text("SELECT (SELECT count(*) FROM assignments) + (SELECT count(*) FROM resolutions)")
        )
    ).scalar_one()
    assert remaining == 0


async def test_delete_engineer_set_null_keeps_history(conn) -> None:
    """Removing an engineer preserves the assignment/resolution rows, attribution only."""
    ward_id, engineer_id = await _seed_ward_user_engineer(conn)
    issue_id = await _seed_issue(conn, ward_id)
    await _seed_assignment_and_resolution(conn, issue_id, engineer_id)

    await conn.execute(text("DELETE FROM engineers WHERE id = :id"), {"id": engineer_id})

    row = (
        await conn.execute(
            text(
                "SELECT "
                "(SELECT engineer_id FROM assignments WHERE issue_id = :i) AS a_eng, "
                "(SELECT engineer_id FROM resolutions WHERE issue_id = :i) AS r_eng, "
                "(SELECT count(*) FROM assignments WHERE issue_id = :i) AS a_cnt, "
                "(SELECT count(*) FROM resolutions WHERE issue_id = :i) AS r_cnt"
            ),
            {"i": issue_id},
        )
    ).one()
    assert (row.a_eng, row.r_eng) == (None, None)  # rows survived, attribution nulled
    assert (row.a_cnt, row.r_cnt) == (1, 1)