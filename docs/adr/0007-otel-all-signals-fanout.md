# ADR-0007: All three signals over OTLP; drop the Prometheus scrape path

- **Status**: Accepted
- **Date**: 2026-10-16

## Context

[ADR-0001](0001-observability-3-layer-otel.md) settled the 3-layer shape — app →
collector → New Relic — and made two choices that this ADR revisits:

1. **Logs and traces travelled OTLP, but metrics did not.** The app exposed a
   Prometheus `/metrics` endpoint (via `prometheus-fastapi-instrumentator`,
   Bearer-gated by `METRICS_TOKEN`) and the collector *scraped* it. That meant
   two metric paths (an HTTP scrape and the OTLP push used by everything else),
   two auth stories, and a second package (`prometheus-fastapi-instrumentator`
   + `prometheus-client`) whose lifecycle/version had to be tracked separately.
2. **The collector was single-sink and volatile.** Only `otlphttp/newrelic`
   existed, with no persistent queue: a New Relic outage dropped telemetry once
   the in-memory retry window (`max_elapsed_time`) expired, and a collector
   restart dropped whatever was buffered. The Grafana "second sink" was a
   commented stub.

The goals for this change were: **one vendor-neutral transport for every
signal**, **no vendor lock-in** (swapping or adding a sink is a collector change,
never an app change), and **survivability at scale** (a sink outage or restart
loses as little telemetry as possible) — without regressing the fail-open
guarantees ADR-0001 established.

## Decision

Make OTLP the **only** telemetry egress from the app and harden the collector:

- **Metrics move onto OTLP.** `src/core/observability.py` gains
  `setup_otlp_metrics()` (a `MeterProvider` + `PeriodicExportingMetricReader`
  exporting to the collector's `/v1/metrics`), and a pure-ASGI
  `OTelMetricsMiddleware` records `http.server.requests` and
  `http.server.request.duration`. **The `/metrics` endpoint,
  `MetricsAuthMiddleware`, the `METRICS_TOKEN` / `ENABLE_PROMETHEUS` settings and
  the `prometheus-fastapi-instrumentator` dependency are removed.**
- **One resource for all three signals.** Logs, traces and metrics share
  `service.name` / `service.version` / `deployment.environment`
  (`_service_resource()`), so they are correlatable in the sink.
- **The collector is the only vendor-aware component.** Its pipelines take all
  three signals from the single `otlp` receiver; adding or swapping a sink is an
  exporter-list edit. The collector gains a **`file_storage` persistent queue**
  (`sending_queue` with `storage: file_storage`, backed by a compose volume) so
  buffered telemetry survives a sink outage up to `max_elapsed_time` and a
  collector restart, plus gzip compression. A **Grafana Cloud fan-out is wired as
  a ready second exporter** (uncomment + set `GRAFANA_OTLP_*`), documenting the
  no-lock-in swap.
- **Split health probes.** `/health/live` is liveness (never touches a
  datastore); `/health/ready` is readiness (dependency-aware). `/health` is kept
  unchanged for back-compat with the Docker `HEALTHCHECK` and the deploy
  workflow.
- **Redact credentials in logs.** A shared `SensitiveDataFilter`
  (`src/log_utils/redaction.py`) is attached to the console, file and OTLP
  handlers, so a secret logged via `extra={...}` is scrubbed before it reaches
  any sink.

Basicauth on the collector's OTLP receiver remains an opt-in (documented, off by
default): enabling it requires matching the app's `NEW_RELIC_OTLP_HEADERS`, and
an open receiver on a private network is the sane default for local dev.

## Consequences

### Gold

- **One transport, one auth story, one place to change vendors.** Every signal
  leaves the app as plain OTLP; the app holds no vendor credential and no
  vendor-specific client.
- **Cardinality is controlled at the source.** Metrics are labelled with the
  matched **route template** (`/api/v1/issues/{issue_id}`), never the raw path,
  so path parameters cannot explode the series count — the failure mode that
  makes metrics expensive at scale.
- **Telemetry survives sink outages and restarts** (disk-backed sending queue),
  and traces are still tail-sampled before they leave the network boundary.
- **Fewer dependencies and one fewer endpoint to secure.** Dropping the
  instrumentator removes `prometheus-client` and the Bearer-gated `/metrics`
  surface entirely.
- **A second sink is a config edit**, not a code change — the concrete answer to
  "no vendor lock-in".

### Trade-offs

- **No vendor-neutral scrape endpoint remains.** A Prometheus/Grafana agent
  inside the network can no longer scrape the app directly; it must receive
  metrics from the collector's OTLP fan-out (Grafana Cloud, or a collector
  `prometheus` exporter). This is the explicit cost of a single pipeline, and it
  is recoverable purely in collector config.
- **Pull-based debugging is gone.** "`curl /metrics`" no longer works; the local
  view is now the collector's `debug` exporter. Debug builds can re-add a
  `prometheus` exporter to the collector if a scrape view is ever needed.
- **The two new metrics are hand-rolled**, so they carry the RED essentials
  (count, duration, status, route) rather than the instrumentator's broader
  default set. Anything else must be added as another OTel instrument.
- **`file_storage` is a new operational surface**: the queue directory must be
  volume-backed and bounded (`queue_size`), or a long outage can fill the disk.
  The compose service mounts `otelcol-queue` and caps the queue at 5000 batches.
  It must also be **writable by the collector uid (10001)**: a fresh named
  volume inherits the *image's* ownership at the mount path, so compose builds
  `docker/otel-collector.Dockerfile`, which pre-creates the directory with
  that owner. Against the bare upstream image the directory is root-owned and
  the collector exits at startup with `open ...: permission denied` — no
  `/healthz`, and the only symptom is a quietly empty sink (the trap Nexus
  documented in its compose comments).
