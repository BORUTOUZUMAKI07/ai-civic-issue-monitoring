# ADR-0008: Authenticate the OTLP receiver; keep second sinks and error tracking opt-in

- **Status**: Accepted
- **Date**: 2026-10-16

## Context

[ADR-0007](0007-otel-all-signals-fanout.md) hardened the *egress* side: all three
signals travel OTLP to a collector that owns the vendor key, queues to disk and
retries through a sink outage. It left the *ingress* side untouched — and that is
the direction a stranger faces.

`docker/otel-collector-config.yaml` exposes `:4317` (gRPC) and `:4318` (HTTP) with
no credential at all. On a shared or public host those ports are reachable by
anyone who can route to them, and an OTLP receiver is not a read endpoint: it
*ingests*. An open one lets a third party POST arbitrary data that

1. consumes the ingest quota the sink's free tier is sized for, and
2. fabricates the very numbers alerts and dashboards are computed from —
   a worse failure than missing telemetry, because nobody investigates it.

Two gaps from the same audit sat alongside it:

- **The "second sink" was never real.** Grafana appeared only as a commented-out
  exporter block. Enabling it naively is impossible by construction: the
  collector refuses to start when an `otlphttp` exporter has an empty endpoint,
  so a default-on fan-out makes the stack unbootable for anyone without Grafana
  credentials — the fail-open guarantee ADR-0001 established would regress the
  moment the file is uncommented.
- **There was no error tracking.** A 500 became a log line nobody reads.

## Decision

### 1. Gate the receiver with HTTP basic auth on both protocols

A `basicauth/server` extension (`htpasswd.inline`) is registered in
`service.extensions`, and **both** the gRPC and HTTP protocols declare
`auth.authenticator: basicauth/server`. The credentials are read from
`OTLP_AUTH_USER` / `OTLP_AUTH_PASSWORD` in the collector and handed to the app
under the same names (`config.py` → `observability.otlp_auth_headers()`), so the
two sides cannot be configured independently without noticing.

The app builds the header only when **both** values are set: a lone user or a
lone password is treated as "no credentials" rather than sent, because a
half-built credential is guaranteed to fail. `NEW_RELIC_OTLP_HEADERS` remains as
a raw escape hatch layered on top (it wins on a key collision).

### 2. Ship the Grafana fan-out as an opt-in overlay file

`docker/otel-collector-config.grafana.yaml` is mounted into the container but
**not** in the default `command`. It carries the `otlphttp/grafana` exporter and
restates all three pipelines with it joined (collector config files are merged:
`exporters` is a union, pipelines are replaced wholesale, which is why the
overlay repeats rather than appends). Enabling it is two credentials plus one
`--config` flag — a collector change, never an app change.

### 3. Add Sentry error tracking, off unless a DSN is set

`setup_sentry()` in `src/core/observability.py` runs at import time in
`main.py`, before the app is built, so startup exceptions are captured too. It
is a strict no-op without `SENTRY_DSN`, fails open if `sentry-sdk` is absent
(it lives in the optional `[observability]` extra), and is idempotent.
`send_default_pii=False` and `SENTRY_TRACES_SAMPLE_RATE=0.0` keep it to what it
is for — grouping *errors* — since traces already travel over OTLP.

### 4. Pin the handshake from both ends in tests

`test_otel_collector_config.py` asserts statically (no Docker) that the receiver
demands auth, that no literal credential is tracked, and that compose hands the
*same* pair to the app and the collector; `test_observability_3layer.py` asserts
the header the app sends. One side without the other is exactly the silent
failure worth a test.

## Consequences

### Gold

- **The receiver stops being a free quota faucet**, and injecting fabricated
  telemetry now requires the credential. The app and the collector read the same
  variable names, so the pair cannot drift without a test noticing it.
- **No literal credential is tracked.** The compose defaults
  (`civicpulse/civicpulse`) are placeholders; the alternative — a hardcoded
  credential in Python — would have shipped in git history permanently.
- **Adding a sink is now a genuinely CI-validated one-flag operation**, which
  the commented-out Grafana stub never was: `test_grafana_fan_out_is_opt_in_and_complete`
  proves the overlay is complete *and* that the default config cannot depend on
  it.
- **Error tracking is opt-in, fail-open and CI-safe.** `sentry-sdk` lives in the
  optional `[observability]` extra, so the default pixi/CI environment carries
  neither the package nor any side effect, while the runtime image (which
  installs `[ml,observability]`) gets it.
- **Config drift now fails a test in the default environment on every push** —
  the place the historical silent failure (an empty `action:` killing the
  collector before `/healthz`) would have been caught.

### Trade-offs

- **The shipped password is guessable by design and must be changed** before any
  deployment that publishes `:4318`. It stops casual abuse, not a determined
  attacker, and basic auth complements network placement rather than replacing
  it.
- **A mismatch is silent from the app's side.** The OTLP exporters do not raise
  on a 401 — they retry and drop — so the symptom is an empty sink, not an
  error. That ambiguity is why the compose env blocks are asserted equal; if it
  ever shows up in production, check `OTLP_AUTH_*` first.
- **Enabling Grafana costs a second `--config` flag.** Deliberately manual: a
  default-on exporter would make the stack unbootable for anyone without
  `GRAFANA_*` credentials.
- **`sentry-sdk` needs an explicit mypy `ignore_missing_imports` entry** and is
  invisible to `pip-audit` in the default environment, since the package is only
  installed in the runtime image.
