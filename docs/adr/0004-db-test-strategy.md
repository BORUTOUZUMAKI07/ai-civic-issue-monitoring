# ADR-0004: DB test strategy — SQLite + in-process fakes by default, Testcontainers for real engines

- **Status**: Accepted
- **Date**: 2026-10-11

## Context

The test suite needs to run everywhere — on a laptop with no Docker, in CI,
and on a developer's machine with a flaky network — while still covering
behavior that only a real database exhibits. The candidate strategies:

- **Always-Testcontainers**: every test against real Postgres/Redis. Highest
  fidelity, but CI- and Docker-dependent, slow, and it punishes every `pytest`
  run with container orchestration.
- **Always-in-memory / fakes**: SQLite `:memory:`, fakeredis, mongomock. Fast
  and hermetic, but silently drifts from production: the project's migrations
  rely on JSONB columns, a Postgres enum, and `ON DELETE` rules (migrations
  005/007/008) that SQLite cannot represent.
- **Layered**: default run hermetic and fast; a small `integration` marker
  buys real engines exactly where schema fidelity matters.

## Decision

Adopt the **3-layer** strategy already implemented in `backend/tests/conftest.py`:

- **Layer 1 (default, `-m 'not integration'`)** — SQLite via
  `sqlite+aiosqlite:///:memory:` for Postgres, `fakeredis` (in-process, RAM
  only) for Redis/Upstash, and `mongomock-motor` for MongoDB. Everything the
  default `pixi run test-ci` runs is hermetic: no network, no Docker, no shared
  state between runs.
- **Layer 2 (mock-integration)** — the `mock_integration` marker exists for
  tests that mock every external service end-to-end; it is registered in
  `pyproject.toml` so `--strict-markers` stays clean.
- **Layer 3 (`integration` marker)** — **Testcontainers** with
  `postgres:16-alpine` and `redis:7-alpine` run the real engines where SQLite
  would lie (see `backend/tests/test_pg_integration.py`: real `alembic upgrade
  head`, JSONB/enum/`ON DELETE` assertions). These self-skip when Docker is
  unavailable rather than fail, so a laptop without Docker stays green.

Two deliberate deletions from scope:

- **MongoDB stays on mongomock.** MongoDB Atlas is a live, credential-owning
  external service and the conftest explicitly avoids touching it in CI
  (`conftest.py` documents this). `mongomock-motor` covers the app's
  fire-and-forget drift logging; if Mongo ever becomes load-bearing (e.g.
  query-critical), a `testcontainers.mongo.MongoContainer` is the documented
  next step, not this ADR's.
- **No always-on aiosqlite+Postgres parity harness.** The integration layer is
  the *only* real-Postgres plane and that is intentional: it keeps the default
  run fast while guaranteeing the schema-level behaviors that matter are still
  asserted somewhere.

## Consequences

### Gold

- `pixi run test-ci` and CI run fully offline and in seconds, directly on any
  machine; contributors never need Docker to see green.
- Schema-heavy behaviors (JSONB, enum, cascade deletes) are asserted against a
  real Postgres in the integration layer instead of being silently assumed.
- Failure is loud in the right place: a migration-only incompatibility is
  caught by the real-Postgres layer; everything else stays hermetic and
  debuggable.

### Trade-offs

- **Fidelity gap in the default layer**: SQLite is not Postgres (no JSONB, no
  enum, different concurrency semantics), and fakeredis is not Redis (no real
  network, no persistence). The suite accepts this by construction — it is the
  price of hermetically running everywhere.
- MongoDB behavior beyond mongomock's surface is *unverified*. Accepted while
  Mongo remains a non-critical log sink; revisit if it becomes load-bearing.
- Layer 3 adds container orchestration time in CI (and Docker on the dev
  machine for anyone running `test-integration` locally) — bounded, but real.