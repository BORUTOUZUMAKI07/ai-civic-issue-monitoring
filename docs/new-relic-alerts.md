# New Relic alerts and runbooks

CivicPulse exports logs, metrics and traces directly to New Relic's OTLP/HTTP
ingest. `observability/new-relic-alerts.json` is the checked-in source of truth
for the alert policy; this document explains each query and what to do when it
fires. [ADR-0009](adr/0009-direct-otlp-ingest.md) records why production exports
directly instead of going through a Render-hosted collector (free services sleep
and drop cold-start telemetry); the collector in `docker/` is local-Compose only.

## Data assumptions

- `service.name` is `CivicPulse-API` (`NEW_RELIC_APP_NAME`).
- All three signals use one resource, so a `correlation_id` on a request log can
  be followed to its span and metrics.
- Export is fail-open. A telemetry outage must not remove the API from service.

Quick checks (no secrets in the URL):

```text
GET https://civicpulse-api-wknx.onrender.com/health
GET https://civicpulse-api-wknx.onrender.com/health/telemetry
GET https://civicpulse-api-wknx.onrender.com/api/v1/auth/oauth/providers
GET https://civicpulse-api-wknx.onrender.com/api/v1/ml/info
```

`/health/telemetry` returns `status: ok` only when the startup probe flushed
logs, metrics and traces successfully. `degraded` or `disabled` is diagnostic,
not a traffic gate.

To inspect what actually arrived in New Relic:

```sql
SELECT uniques(metricName) FROM Metric WHERE service.name = 'CivicPulse-API'
SELECT * FROM Metric WHERE metricName = 'http.server.requests' LIMIT 1
SELECT count(*) FROM Log WHERE service.name = 'CivicPulse-API' FACET event_type
```

## Creating the alerts

1. In New Relic, open **Alerts & AI → Policies → New policy** and name it
   `CivicPulse Production Observability`.
2. For each entry in `observability/new-relic-alerts.json`, add a **NRQL alert
   condition** with that `name`, `nrql`, severity and threshold.
3. Set the runbook URL to the anchor listed on the condition.
4. Use **Per condition** incident preference so a latency warning and a 5xx
   critical page independently.

The conditions are intentionally coarse: free Render services sleep and cold
starts produce a short burst of slow requests. Each condition uses a 5–10 minute
duration window to avoid paging on a single cold start.

## 5xx error rate

```sql
FROM Metric
SELECT 100.0 * filter(sum(http.server.requests), WHERE `http.response.status_code` >= 500)
       / sum(http.server.requests)
WHERE metricName = 'http.server.requests' AND service.name = 'CivicPulse-API'
```

Threshold: **above 5% for 5 minutes** (critical).

Runbook:

1. Check `/health` and `/health/telemetry`.
2. Find the failing route:
   `FROM Log SELECT count(*) WHERE event_type = 'request_exception' FACET http_path`.
3. Read the matching trace by `correlation_id`; `request_exception` logs carry
   the same ID as the HTTP response header.
4. If the errors are `frontend_error` reports rather than backend exceptions,
   follow the frontend errors runbook below.
5. Roll back the last backend deploy if the spike started at a deploy boundary.

## p95 latency

```sql
FROM Metric
SELECT percentile(http.server.request.duration, 95)
WHERE metricName = 'http.server.request.duration' AND service.name = 'CivicPulse-API'
```

Threshold: **above 2 seconds for 10 minutes** (warning). Values are seconds.

Runbook:

1. Facet the same metric by `http.route` to find the slow endpoint.
2. Check dependency transitions:
   `FROM Log SELECT count(*) WHERE event_type = 'dependency_degraded' FACET dependency`.
3. If ML inference is involved, check `/api/v1/ml/info` for ONNX vs. fallback.
4. A cold start alone should settle within the 10-minute window; do not restart
   the service just because of the first slow request after idle.

## Health failures

```sql
FROM Log
SELECT count(*)
WHERE event_type IN ('health_check_failure', 'dependency_degraded')
  AND service.name = 'CivicPulse-API'
```

Threshold: **above 0 for 5 minutes** (critical).

Runbook:

1. Call `/health`; a 503 includes which components failed.
2. Check the dependency runbook below for the named component.
3. Verify Render has not silently restarted the service into a bad config:
   check the deploy log and that `REDIS_URL` is still the Upstash `rediss://`
   TCP URL (REST-only variables must stay unset).

## Postgres, Redis, or MongoDB degradation

```sql
FROM Log
SELECT count(*)
WHERE event_type = 'dependency_degraded'
  AND dependency IN ('database', 'redis', 'mongodb')
  AND service.name = 'CivicPulse-API'
FACET dependency
```

Threshold: **above 0 for 5 minutes** (warning).

Runbook:

- `database` (Neon Postgres): check the Neon branch is awake and the pooled
  `DATABASE_URL` is valid. Confirm migrations are at head in the Render deploy
  log; the image runs `alembic upgrade head` before uvicorn starts.
- `redis` (Upstash): confirm the free instance is not paused and `REDIS_URL`
  starts with `rediss://`. Pub/Sub needs the TCP client, not the REST client.
- `mongodb` (Atlas): confirm the cluster is not paused, the SRV URI is correct,
  and the `civicpulse_analytics` database is reachable from Render's region.

Transitions are logged once, so `dependency_recovered` in the same time window
means the incident is over.

## Frontend errors

```sql
FROM Log
SELECT count(*)
WHERE event_type = 'frontend_error' AND service.name = 'CivicPulse-API'
```

Threshold: **above 20 in 5 minutes** (warning).

Browser errors travel `browser → /api/client-errors → backend structured log →
OTLP`; no vendor key is present in the browser. Each report is scrubbed and its
query string removed before logging.

Runbook:

1. Facet by `frontend_event_type` and `frontend_path` to find the affected page.
2. Join to `api_error` reports by `correlation_id` to see the backend response.
3. Reproduce on the canonical frontend:
   `https://civicpulse-civic-ai8.vercel.app`.
   Do not use `https://civicpulse.vercel.app`; that is a different project.

## Startup telemetry verification failed

```sql
FROM Log
SELECT count(*)
WHERE event_type = 'startup_telemetry_verification'
  AND telemetry_ok = false
  AND service.name = 'CivicPulse-API'
```

Threshold: **above 0 for 5 minutes** (warning).

On every boot the app emits one span, one metric and one log, force-flushes each
provider, and records the result in `startup_telemetry_verification`. The same
snapshot is served by `/health/telemetry`.

Runbook:

1. Check `enabled`, `endpoint_configured`, `traces_ok`, `metrics_ok` and
   `logs_ok` on `/health/telemetry`.
2. If `enabled` is false, check Render's `NEW_RELIC_ENABLED` value.
3. If `endpoint_configured` is false, check `NEW_RELIC_OTLP_ENDPOINT` is
   `https://otlp.nr-data.net:4318`.
4. If only some signals fail, check that `NEW_RELIC_OTLP_HEADERS` contains the
   `api-key` header and that the optional Basic-auth pair is complete (both
   values set or both empty).
5. Confirm the deployed image includes the `[observability]` extras; the backend
   Dockerfile installs them.
6. Redeploy after fixing. A successful boot emits a new verification event with
   `telemetry_ok = true`.
