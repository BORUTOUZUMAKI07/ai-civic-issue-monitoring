# ADR-0006: CI load-test gate on the Locust suite with P95 / error-rate budgets

- **Status**: Accepted
- **Date**: 2026-10-11

## Context

The repo already shipped a Locust load-test suite
(`backend/scripts/loadtest/locustfile.py`) and a `loadtest` pixi feature
(`locust>=2.31.0`), but nothing ran it in CI. A regression that makes read
paths collapse under load — a missing cache, an unbounded query, an extra
synchronous fan-out per request — is invisible to unit tests, which run against
in-process fakes and SQLite. Meanwhile unit-test boundaries would not catch "the
same app, real Postgres, real Redis, 20 users" slowness.

Two candidate load tools were discussed: **k6** (single foreign binary, new
toolchain, new script format) and **Locust** (already in the repo, Python, the
existing suite already models an authenticated reporter). Using what exists is
cheaper and keeps the load scripts reviewable by the same Python reviewers as
the app.

The constraint that shaped the design: **square the suite's auth requirement
against a throwaway CI database.** The Locust tasks need a real account to
exercise the authenticated read paths (`/issues`, `/dashboard/stats`,
`/dashboard/heatmap`, `/issues/search`), and `/health` alone is a weak perf
signal. The app auto-creates schema on boot in non-`production` environments
(`init_db`), so no Alembic migration step is needed in CI.

## Decision

Add a **`performance-loadtest`** job to `.github/workflows/ci.yml` and wire it
into the Docker jobs' `needs`, so images only ship when the performance gate is
green:

1. **Real engines, no elaborate fixtures**: GitHub Actions `services` provide
   `postgres:16` and `redis:7` (the same images/creds as `backend-test`).
   MongoDB is absent on purpose — drift logging is fail-open, so the app boots
   and serves without it.
2. **Boot the real app**: `uvicorn src.main:app` from the `default` pixi env
   against those services, with `ENVIRONMENT=development` (schema auto-create),
   a generous rate-limit budget (`RATE_LIMIT_*` raised via env so 20 users from
   `127.0.0.1` don't trip the token bucket and turn the perf run into a
   throttle test), and empty LLM keys (the app fails open).
3. **Seed one account**: `backend/scripts/loadtest/seed_user.py` inserts a
   `field_worker` user via the app's own models + `hash_password`, after the
   server reports healthy. `LOCUST_EMAIL`/`LOCUST_PASSWORD` then light up the
   authenticated tasks.
4. **Run Locust headless**: `pixi run -e loadtest loadtest --headless -u 20 -r 5
   -t 120s --host http://127.0.0.1:8000 --csv ... --html ...` — the existing
   suite unchanged.
5. **Assert budgets**: `backend/scripts/loadtest/run_gate.py` parses Locust's
   `*_stats.csv` and fails the job unless global error % is ≤ 1% and P95 is
   under per-endpoint budgets (health vs. authed API), all env-overridable
   (`LOADTEST_MAX_ERROR_PCT`, `LOADTEST_P95_HEALTH_MS`, `LOADTEST_P95_API_MS`).
   Locust itself has no built-in fail-on-threshold, so the gate is a thin
   stdlib-only parser.
6. **Artifacts**: stats CSV + HTML report upload on completion (success or
   failure), so a breached budget is debuggable from the run itself.

## Consequences

### Gold

- **A real performance regression guard on every PR/push to main.** The gate
  uses production-shaped engines and the actual HTTP API — the gap unit tests
  cannot see.
- Zero new tooling: Locust was already there; the gate is two small Python
  scripts (stdlib parsing) and one job.
- Thresholds are tunable per-deployment without touching code (env vars), so a
  slow CI runner can be calibrated rather than fought.
- Bonus coverage: the job exercises the new plain-Redis path from ADR-0005
  against a real Redis and the Postgres engine in one shot.

### Trade-offs

- **~4–5 minutes added to CI** (env install ×2 + runtime + load). Priced in,
  and it gates Docker image publication, not just PR checks.
- **A flaky CI runner can flunk the gate.** Budgets are per-endpoint P95 and
  global error rate; tuned for a 2-core ubuntu runner with local Postgres/Redis
  round-trips (~sub-second), but any shared-runner hiccup can burn a retry.
  Calibration knobs exist for exactly this.
- The gate asserts *latency and error envelopes under a modest synthetic
  workload* (20 users / ~120 s), not capacity planning (max RPS). That is the
  right scope for a tripwire; load *testing* remains a manual
  `pixi run -e loadtest loadtest` activity.
- Search uses the keyword fallback in CI (no embeddings configured), so it
  exercises the query path without the LLM/embedding dependency — a documented
  simplification, not a silent one.