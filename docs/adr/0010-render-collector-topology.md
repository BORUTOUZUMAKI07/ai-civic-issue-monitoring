# ADR-0010: Separate free Render collector with its own CI-gated deploy hook

- **Status**: Accepted
- **Date**: 2026-11-27
- **Supersedes**: [ADR-0009](0009-direct-otlp-ingest.md) (direct production ingest)
- **Restores**: the production deployment shape of
  [ADR-0001](0001-observability-3-layer-otel.md),
  [ADR-0007](0007-otel-all-signals-fanout.md) and
  [ADR-0008](0008-otlp-receiver-auth-and-opt-in-sinks.md)

## Context

ADR-0001 put an OpenTelemetry collector between the app and New Relic so the
application process would never hold the vendor credential. ADR-0007 moved all
three signals (logs, metrics, traces) onto OTLP and removed the uncollected
Prometheus scrape path; ADR-0008 authenticated the public receiver and made a
second sink opt-in.

ADR-0009 then removed the collector from production and pointed the backend
straight at `https://otlp.nr-data.net:4318`. Its reason was cold starts: free
Render web services sleep after 15 minutes idle, and a sleeping collector cannot
replay telemetry the app emitted while the receiver was unavailable.

The user subsequently asked for the Nexus/LinkForge-style topology used by the
sister project: a **separate collector service with its own deploy hook**. When
offered an always-on paid collector versus a free one that sleeps, the user
chose **free anyway** and accepted that cold-start telemetry can be lost. The
constraints that must not regress are:

- **Fail-open**: telemetry problems never remove a working API from service.
- **No vendor key in the browser** (or, after this change, in the backend).
- **No Prometheus scrape path**: no scraper is deployed, so a pull endpoint
  would collect nothing.
- **A diagnostic-only** `/health/telemetry` that never gates traffic.
- **CI-gated production deploys only**: no platform-native auto-deploy and no
  staging target.

## Decision

Production uses two free Render web services: `civicpulse-api` and
`civicpulse-otel-collector`. The backend sends all three signals over OTLP/HTTP
to the collector; the collector owns the New Relic license key and forwards them
with its `otlphttp/newrelic` exporter.

1. **One collector config, two hosts.** `docker/otel-collector-config.yaml` is
   reused unchanged by Compose and by the Render image
   (`docker/otel-collector.Dockerfile`). Its OTLP/HTTP receiver binds
   `0.0.0.0:${env:PORT}` because Render injects a dynamic `PORT` and maps public
   HTTPS to it; Compose sets `PORT=4318` so the local URL stays
   `http://otel-collector:4318`. Hard-coding 4318 in production would leave the
   service unreachable. The same config stamps `service.name` from
   `${env:NEW_RELIC_APP_NAME}`; both hosts set it to `CivicPulse-API`, matching
   `observability/new-relic-alerts.json`, so the collector cannot silently move
   telemetry out from under the alert queries.
2. **No healthCheckPath.** Render probes the injected `$PORT`, which is occupied
   by the OTLP receiver. The collector's `health_check` extension stays on
   internal `:13133` for local diagnostics. Render displays the service as Live
   when the port is bound, and its logs contain `Everything is ready` once all
   pipelines and the file-backed queue are writable.
3. **Key and auth boundaries.** `NEW_RELIC_LICENSE_KEY`, `OTLP_AUTH_USER` and
   `OTLP_AUTH_PASSWORD` are prompted secrets on the collector. The backend
   receives the same `OTLP_AUTH_*` pair so `otlp_auth_headers()` builds the
   matching Basic header, but receives **no** `NEW_RELIC_OTLP_HEADERS` at all.
   Literal credentials remain out of Git; a mismatch is a 401 the exporters
   retry and drop, so the pair is guarded by static tests and the runbook.
4. **Third deploy hook.** `.github/workflows/production-deploy.yml` requires
   `COLLECTOR_DEPLOY_HOOK_URL` alongside `RENDER_DEPLOY_HOOK_URL` and
   `VERCEL_DEPLOY_HOOK_URL`. It verifies all three before contacting any
   platform (failing closed when one is absent), then triggers collector →
   backend → frontend. Both Render services set
   `autoDeployTrigger: "off"`; Vercel sets `git.deploymentEnabled: false`.
   Dispatch is still gated on a green `CI` run on `main`, with a manual
   `workflow_dispatch` escape hatch.
5. **Unchanged app contract.** The app continues to export logs, metrics and
   traces from one choke point (`backend/src/core/observability.py`) with one
   resource and no Prometheus endpoint. Browser errors travel through the BFF
   into structured logs; a browser `X-Correlation-ID` is used only when it is a
   valid UUID, otherwise the backend generates one. No OTLP credential is
   exposed to the browser.

## Consequences

### Gold

- **Nexus/LinkForge parity.** Sink selection, sampling and fan-out are collector
  decisions; swapping vendors is a collector config edit, not an app rewrite.
- **The vendor key is isolated to one service.** Neither the backend process nor
  the browser bundle can leak the New Relic license key.
- **Disk-backed queue and tail sampling are back in production.** A sink outage
  within a running instance is buffered and retried, and errors/slow traces are
  kept while ~10% of the rest is sampled before the free ingest quota is used.
- **Every deploy remains gated and auditable.** One CI-green `main` tip triggers
  three branch-scoped hooks; a missing secret stops the workflow before any
  platform is contacted.

### Trade-offs

- **Cold-start telemetry loss is explicitly accepted.** The collector sleeps
  after 15 minutes idle. Hooks return on acceptance, not readiness, so the
  backend's first 10-second OTLP timeout can fire before the collector wakes.
  A short `degraded`/`disabled` window in `/health/telemetry` after idle is
  expected; it is diagnostic and never removes the API from rotation.
- **The disk-backed queue is process-local on Render.** Free services have no
  durable disk, so a restart still loses anything not yet flushed, even though
  the queue protects against sink outages while the instance is alive.
- **More surfaces to configure.** Two Render services, three hook secrets and an
  auth pair entered in two places must agree. Static guards cover the tracked
  configuration; the operator still enters the secret values.
- **The backend depends on a public hostname.** If Render adds a suffix to
  `civicpulse-otel-collector.onrender.com`, `NEW_RELIC_OTLP_ENDPOINT` must be
  updated to the exact hostname shown. Deploy hooks do not apply changed
  Blueprint env values to an existing service; sync or edit the Environment tab
  explicitly.
- **New Relic remains the production sink and the alert source.** The Grafana
  overlay is opt-in and no alternate production sink or Prometheus scraper was
  added; `docs/new-relic-alerts.md` remains the runbook.
