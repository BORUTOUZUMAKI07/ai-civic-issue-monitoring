# ADR-0009: Direct OTLP ingest in production; keep the collector local-only

- **Status**: Superseded by [ADR-0010](0010-render-collector-topology.md)
- **Date**: 2026-11-27
- **Supersedes**: [0001](0001-observability-3-layer-otel.md) and the production
  deployment shape of [0007](0007-otel-all-signals-fanout.md) /
  [0008](0008-otlp-receiver-auth-and-opt-in-sinks.md) (both remain current for
  the collector config; ADR-0010 runs it in production too)

> This decision was reversed on the same day: the user chose the
> Nexus/LinkForge-style separate collector and explicitly accepted the free
> tier's cold-start telemetry loss. Read this ADR only to understand why the
> direct path existed; ADR-0010 is the current production design.

## Context

[ADR-0001](0001-observability-3-layer-otel.md) put a collector between the app
and the sink so the app would never hold a vendor credential.
[ADR-0007](0007-otel-all-signals-fanout.md) moved all three signals onto OTLP and
gave that collector a disk-backed queue;
[ADR-0008](0008-otlp-receiver-auth-and-opt-in-sinks.md) gated its receiver and
made a second sink opt-in. That shape works for the local Compose stack, where
the collector is a container on the same host.

Production is a different environment: Render's web service is free-tier and
**sleeps after 15 minutes idle**. Hosting the collector as a second free Render
service means it sleeps too. A cold start does not replay whatever the app tried
to export while the receiver was unavailable: the first spans, metrics and logs
of a request are dropped, which is exactly the traffic most worth observing.
Running one combined container would remove the hop but still leave a single
cold-starting process, and a disk-backed queue inside an ephemeral free-tier
filesystem buys nothing after the instance restarts.

The constraints that must not regress are:

- **Fail-open**: a telemetry outage must never remove a working API from
  service.
- **No vendor key in the browser**: browser errors still travel through the BFF
  into backend structured logs.
- **No Prometheus scrape path**: there is no scraper deployed, so adding a pull
  endpoint would create metrics nobody collects.
- **A diagnostic health surface**: `/health/telemetry` reports the startup
  verification but never gates traffic.

## Decision

In production, export logs, metrics and traces **directly** from the FastAPI
process to New Relic's OTLP/HTTP ingest:

- `NEW_RELIC_ENABLED=true`, `NEW_RELIC_OTLP_ENDPOINT=https://otlp.nr-data.net:4318`,
  and `NEW_RELIC_OTLP_HEADERS={"api-key":"<license key>"}` are set as Render
  service environment variables (secrets in the platform, never in Git). The
  app remains the only component that knows the vendor endpoint and key.
- **No Render-hosted collector.** The collector configuration, its `basicauth`
  receiver and its Grafana overlay stay in `docker/` for local Compose only.
  ADR-0007's "one resource for all three signals" and no-Prometheus decisions
  still hold; only the egress hop changes.
- Export stays fail-open. On boot the app emits one span, one metric and one log,
  force-flushes each provider, and publishes the result at `/health/telemetry`
  and as a `startup_telemetry_verification` log. `degraded`/`disabled` is a
  signal for an operator, not a reason to fail liveness or readiness.
- Browser errors go `browser → /api/client-errors (Next route) → backend
  /api/v1/observability/client-errors → structured log → OTLP`. The BFF relay is
  scrubbed and its query string dropped; a browser
  `X-Correlation-ID` is accepted only when it is a valid UUID, otherwise the
  backend generates one. No ingest credential is ever sent to a browser.
- Alerts are defined against New Relic NRQL in
  `observability/new-relic-alerts.json`; see `docs/new-relic-alerts.md` for the
  runbooks. There is no alternate production sink and no scraper to deploy.

## Consequences

### Gold

- **Cold starts are observable.** The first request after idle is exported by
  the same process that serves it; there is no second service to wake.
- **One less service on the free tier** and one less hop that can fail silently.
- **The browser still holds no vendor key**, and a browser error keeps its
  correlation ID through to the backend log and span.
- **A telemetry outage is still non-fatal.** `/health/telemetry` makes the
  failure diagnosable without making it a traffic gate.
- **Vendor-neutral OTLP is retained at the app boundary**: changing the sink is
  an endpoint/header change, not a rewrite of the instrumentation.

### Trade-offs

- **The local collector no longer mirrors production.** ADR-0007/0008's queue,
  auth handshake and Grafana fan-out are developer conveniences, not production
  guarantees; local telemetry can succeed where production drops events.
- **No durable queue in production.** If New Relic is unreachable, events inside
  the exporter's in-memory retry window are lost rather than spooled to disk.
  This is the accepted cost of fail-open on a free tier.
- **Swapping vendors is now a deployment change** (endpoint and header), not a
  collector config edit. It remains a two-variable change because the app still
  speaks plain OTLP.
- **Alerting depends on a single SaaS.** The free New Relic ingest quota is the
  capacity ceiling; there is no second production sink to fail over to.
