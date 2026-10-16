# ADR-0001: 3-layer OTLP observability (app → collector → New Relic)

- **Status**: Superseded by [ADR-0007](0007-otel-all-signals-fanout.md) (the
  Prometheus `/metrics` scrape path was removed; all three signals now travel
  OTLP)
- **Date**: 2026-10-11

## Context

CivicPulse previously instrumented the backend with the direct New Relic agent
(`newrelic.agent.initialize`), which required the application process to hold
the New Relic `NEW_RELIC_LICENSE_KEY`. That design had two problems:

1. **The vendor credential lived in the app.** Any process that could read the
   app's environment — a compromised dependency, a leaked `.env`, a debugging
   shell — could exfiltrate the key and burn the account.
2. **Tooling lock-in.** Metrics, logs and traces were shaped by what the New
   Relic agent exposed. The sister project (nexus-ai) had standardized on an
   OpenTelemetry-first, 3-layer architecture, and the two codebases were
   drifting apart.

The requirements for the replacement were:

- Keep New Relic as the Layer-3 sink (the team's dashboards/alerts run there).
- The app must never hold the vendor key.
- Metrics must remain Prometheus-shaped (`/metrics` RED endpoint), independent
  of the vendor.
- Any telemetry path must be fail-open: an unconfigured or broken export must
  never break requests, and startup must not require a collector to be present.

## Decision

Adopt the same 3-layer OpenTelemetry pipeline as nexus-ai:

- **Layer 1 (in-process)** — the backend app. It exposes Prometheus RED metrics
  at `/metrics` (Bearer-gated when `METRICS_TOKEN` is set) and exports OTLP
  logs **and traces** over OTLP/HTTP to a Layer-2 collector. All of it is gated
  by `NEW_RELIC_ENABLED` (default `false`) and lives in the optional
  `[observability]` extras (`backend/pyproject.toml`), implemented in
  `backend/src/core/observability.py`.
- **Layer 2 (transport agent)** — an `otel/opentelemetry-collector-contrib`
  container (`docker/otel-collector-config.yaml`, compose service
  `otel-collector`). It owns `NEW_RELIC_LICENSE_KEY`, receives OTLP on :4318,
  scrapes the app's `/metrics`, tail-samples traces (keep all errors, ~10% of
  the rest), and forwards everything to Layer 3.
- **Layer 3 (sink)** — New Relic via the `otlphttp` exporter
  (`https://otlp.nr-data.net:4318`).

Span sources are the FastAPI, httpx and SQLAlchemy OpenTelemetry
instrumentors, registered when tracing is enabled; they give request, outbound
LLM call, and query-level spans without any application code knowing about
telemetry. No Jaeger or second trace backend was added — the existing collector
`traces` pipeline (receiver + `tail_sampling` + `batch` + `resource`) already
carried the whole story.

Fail-open behavior is deliberate and is the same for all three signals:

- `NEW_RELIC_ENABLED` unset (or endpoint empty) → strict no-op.
- Optional extras not installed → logged warning, app proceeds.
- Collector unreachable → telemetry dropped, requests/logging unaffected.

## Consequences

### Gold

- The app holds **no** vendor credential; a leaked app env leaks nothing useful
  to New Relic's API.
- Prometheus `/metrics` remains KPI- and alerting-owner across vendors; New
  Relic is a consumer of the same pipeline, not the origin of it.
- Traces get free-tier-friendly sampling *before* leaving the repo's network
  boundary (the collector's `tail_sampling`), so the free-tier quota is the
  agent's problem, not every request's.
- A fresh dev environment works with zero observability configuration, and
  `docker compose up` boots the whole stack without any New Relic vars.
- `src/core/observability.py` is a single choke point for "how telemetry
  escapes the app", testable with plain monkeypatched settings.

### Trade-offs

- **Silent telemetry loss is the price of fail-open.** A misconfigured
  endpoint or down collector means logs/traces/metrics vanish with only a
  startup warning. Accepted: availability of the API outweighs completeness of
  telemetry, and this matches nexus-ai.
- **One more moving part in the deploy.** The collector is a new required
  container; its `resource` processor `upsert`s `deployment.environment` and
  `service.name`, so those attributes must be consistent between the app and
  the collector config.
- The app's timestamp/`service.name`/`deployment.environment` resource
  attributes are duplicated in the collector for logs/metrics (the collector
  owns the final values). Keeping them aligned is a documented operational
  duty, not an automated invariant.