# Architecture Decision Records

This directory records the significant architecture decisions made for
CivicPulse, in the [Michael Nygard format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
An ADR is written when a decision is *made*, not when it is implemented, so a
future reader (or a reviewer wondering "why does this work this way?") can
recover the trade-offs that a diff no longer shows.

| ADR | Title | Status | Date |
| :-- | :---- | :----- | :--- |
| [0001](0001-observability-3-layer-otel.md) | 3-layer OTLP observability (app → collector → New Relic) | Superseded by 0007/0009 | 2026-10-11 |
| [0002](0002-race-safe-model-loading.md) | Race-safe ML model loading (eager warmup + double-checked locking) | Accepted | 2026-10-11 |
| [0003](0003-ab-testing-design.md) | A/B testing: in-app shadow / traffic-split, no external feature-flag service | Accepted | 2026-10-11 |
| [0004](0004-db-test-strategy.md) | DB test strategy: SQLite + in-process fakes by default, Testcontainers for real engines | Accepted | 2026-10-11 |
| [0005](0005-local-dev-stack-compose.md) | Local dev datastores behind a compose `dev` profile | Accepted | 2026-10-11 |
| [0006](0006-ci-load-test-gate.md) | CI load-test gate on the Locust suite with P95 / error-rate budgets | Accepted | 2026-10-11 |
| [0007](0007-otel-all-signals-fanout.md) | All three signals over OTLP; drop the Prometheus scrape path | Accepted (local Compose; production egress superseded by 0009) | 2026-10-16 |
| [0008](0008-otlp-receiver-auth-and-opt-in-sinks.md) | Authenticate the OTLP receiver; opt-in second sink and error tracking | Accepted (local Compose only) | 2026-10-16 |
| [0009](0009-direct-otlp-ingest.md) | Direct New Relic OTLP ingest in production; collector stays local-only | Accepted | 2026-11-27 |

Statuses: **Accepted** — decided, implemented, and shipped. **Superseded** —
replaced by a later ADR (see that ADR).

## Reading order

For someone new to the codebase the highest-signal entries are:

1. **0004** — explains *why tests use SQLite/fakes and only some tests spin up
   real Postgres/Redis*; it makes the `integration` marker and `conftest.py`
   comprehensible.
2. **0001 → 0007 → 0008 → 0009** — explains how the app ended up with one OTLP
   transport and no Prometheus scrape path, why the local collector owns the
   vendor key and gates its receiver, and why **production** exports directly to
   New Relic instead: a free Render collector would sleep and drop cold-start
   telemetry. 0007/0008 still describe the local Compose stack; 0009 is the
   production path.
3. **0002** — explains the thread-safety contract around ML model loading, which
   the eager-warmup boot path and `predict.py`'s lock both depend on.

## Local conventions

* One directory, numbered prefixes, Markdown files.
* "Status" is the first section. A decision is either accepted or superseded;
  proposed-but-rejected alternatives live in "Context", not in their own ADRs.
* Consequences are split into Gold (positives) and Trade-offs (costs), so the
  balance is explicit rather than buried in prose.