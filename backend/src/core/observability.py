"""Layer-1 -> Layer-2 OTLP export for New Relic (env-gated).

Every line the app logs, every span the instrumentors record, and every RED
metric the HTTP middleware records is forwarded to the Layer-2 OpenTelemetry
collector over OTLP/HTTP (``docker/otel-collector-config.yaml``, the
``otel-collector`` compose service). The collector owns the New Relic ingest
key and fans the three signals out, so the app never holds a vendor credential
and never speaks a vendor protocol -- only standard OTLP.

Deliberately fail-open, in keeping with the rest of the stack:

* Gated by ``NEW_RELIC_ENABLED``; unset, or with no ``NEW_RELIC_OTLP_ENDPOINT``,
  it is a strict no-op.
* When enabled but the optional ``[observability]`` extras are not installed it
  degrades to a logged warning, never an exception.
* Export problems never affect requests or logging -- a broken collector drops
  telemetry, not log lines.

This module is the single choke point for "how telemetry escapes the app": all
three signals share one resource (service.name/version/environment) and one
endpoint. There is no Prometheus scrape path -- metrics travel the same OTLP
route as logs and traces.
"""

from __future__ import annotations

import base64
import logging
import warnings
from typing import Any

from src.core.config import settings

logger = logging.getLogger("civicpulse")

_otlp_handler: logging.Handler | None = None
_otlp_provider: Any = None
_otlp_trace_provider: Any = None
_otlp_metrics_provider: Any = None
_http_server_requests: Any = None
_http_server_duration: Any = None


def _otlp_base_endpoint() -> str | None:
    """The collector's OTLP/HTTP base URL, or ``None`` when unconfigured."""
    base = (settings.NEW_RELIC_OTLP_ENDPOINT or "").strip().rstrip("/")
    return base or None


def _otlp_logs_endpoint() -> str | None:
    base = _otlp_base_endpoint()
    if base is None:
        return None
    return f"{base}/v1/logs"


def _otlp_metrics_endpoint() -> str | None:
    base = _otlp_base_endpoint()
    if base is None:
        return None
    return f"{base}/v1/metrics"


def otlp_auth_headers() -> dict[str, str] | None:
    """The ``Authorization: Basic`` header for a basicauth-gated receiver.

    Returns ``None`` unless *both* ``OTLP_AUTH_USER`` and
    ``OTLP_AUTH_PASSWORD`` are set: a lone user or a lone password is a
    half-finished configuration, and sending it would produce a credential the
    collector is guaranteed to reject. Shared by all three signals so logs,
    traces and metrics authenticate identically.
    """
    user = (settings.OTLP_AUTH_USER or "").strip()
    secret = settings.OTLP_AUTH_PASSWORD or ""
    if not user or not secret:
        return None
    token = base64.b64encode(f"{user}:{secret}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _otlp_headers() -> dict[str, str] | None:
    """Extra headers for every OTLP request, or ``None`` when none apply.

    The derived Basic header (from ``OTLP_AUTH_*``) covers the common case --
    the collector's receiver is basicauth-gated. ``NEW_RELIC_OTLP_HEADERS`` is
    a raw escape hatch layered on top and wins on a key collision.
    """
    headers: dict[str, str] = dict(otlp_auth_headers() or {})
    headers.update(settings.NEW_RELIC_OTLP_HEADERS)
    return headers or None


def _service_resource() -> Any:
    """The shared OTel resource for all three signals.

    One resource keeps logs, traces and metrics correlatable in the sink; the
    collector's ``resource`` processor ``upsert``s the same two keys, so the
    values must stay aligned.
    """
    from opentelemetry.sdk.resources import Resource

    return Resource.create(
        {
            "service.name": settings.NEW_RELIC_APP_NAME or settings.PROJECT_NAME,
            "service.version": settings.VERSION,
            "deployment.environment": settings.ENVIRONMENT,
        }
    )


def setup_otlp_log_handler(log_level: int = logging.INFO) -> logging.Handler | None:
    """Attach an OTLP log handler to the root stdlib logger (once).

    Returns the attached handler, or ``None`` when the export is disabled,
    unconfigured, or the OTel extras are missing. Calling again returns the
    already-attached handler; :func:`shutdown_otlp_log_handler` resets the
    state so wiring can be redone (used by tests and the shutdown path).
    """
    global _otlp_handler, _otlp_provider
    if _otlp_handler is not None:
        return _otlp_handler
    if not settings.NEW_RELIC_ENABLED:
        return None
    endpoint = _otlp_logs_endpoint()
    if endpoint is None:
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        exporter = OTLPLogExporter(endpoint=endpoint, timeout=10, headers=_otlp_headers())
        processor = BatchLogRecordProcessor(
            exporter,
            schedule_delay_millis=settings.NEW_RELIC_EXPORT_INTERVAL_SECONDS * 1000,
        )
        provider = LoggerProvider(resource=_service_resource())
        provider.add_log_record_processor(processor)
        # The SDK's stdlib handler is deprecated in favour of the
        # opentelemetry-instrumentation-logging package; it is functionally
        # correct here, so silence the advisory warning rather than add a dep.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            handler = LoggingHandler(level=log_level, logger_provider=provider)
        logging.getLogger().addHandler(handler)
        _otlp_handler = handler
        _otlp_provider = provider
        logger.info("OTLP log handler wired to %s", endpoint)
        return handler
    except Exception as exc:  # noqa: BLE001 - fail-open seam
        logger.warning("OTLP log handler wiring failed: %s", exc)
        return None


def shutdown_otlp_log_handler() -> None:
    """Detach the OTLP handler and flush/shutdown the log pipeline.

    Idempotent and safe to call when nothing was ever wired.
    """
    global _otlp_handler, _otlp_provider
    handler = _otlp_handler
    provider = _otlp_provider
    _otlp_handler = None
    _otlp_provider = None
    if handler is None:
        return
    try:
        logging.getLogger().removeHandler(handler)
        handler.close()
    except Exception as exc:  # noqa: BLE001 - teardown must never break shutdown
        logger.warning("OTLP log handler teardown failed: %s", exc)
    if provider is not None:
        try:
            provider.force_flush()
            provider.shutdown()
        except Exception as exc:  # noqa: BLE001
            logger.warning("OTLP log provider shutdown failed: %s", exc)


def setup_otlp_tracing(app: Any) -> Any | None:
    """Wire OTLP span export (Layer 1 -> Layer 2) for a FastAPI app.

    Env-gated exactly like the log handler. When active it:

    * creates a ``TracerProvider`` that exports to the collector's ``/v1/traces``
      and sets it as the global provider (so the SDK's auto-instrumentation and
      any ``@tracer.start_as_current_span`` calls share the same pipeline), and
    * registers the FastAPI, httpx and SQLAlchemy instrumentors, so inbound
      HTTP, outbound LLM calls and query execution become spans without the app
      knowing anything about telemetry.

    Returns the provider (or the already-wired one), or ``None`` when disabled,
    unconfigured, or an extras/instrumentation problem occurred — fail-open:
    a missing instrumentor logs and continues with the rest.
    """
    global _otlp_trace_provider
    if _otlp_trace_provider is not None:
        return _otlp_trace_provider
    if not settings.NEW_RELIC_ENABLED:
        return None
    endpoint = _otlp_base_endpoint()
    if endpoint is None:
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=_service_resource())
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", timeout=10, headers=_otlp_headers()),
                schedule_delay_millis=settings.NEW_RELIC_EXPORT_INTERVAL_SECONDS * 1000,
            )
        )
        trace.set_tracer_provider(provider)
        _otlp_trace_provider = provider

        instrumented: list[str] = []
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
            instrumented.append("fastapi")
        except Exception as exc:  # noqa: BLE001 - fail-open seam
            logger.warning("FastAPI instrumentation unavailable: %s", exc)
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
            instrumented.append("httpx")
        except Exception as exc:  # noqa: BLE001 - fail-open seam
            logger.warning("httpx instrumentation unavailable: %s", exc)
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            from src.core.database import engine

            SQLAlchemyInstrumentor().instrument(engine=engine)
            instrumented.append("sqlalchemy")
        except Exception as exc:  # noqa: BLE001 - fail-open seam
            logger.warning("SQLAlchemy instrumentation unavailable: %s", exc)

        logger.info(
            "OTLP trace export wired to %s (instrumented: %s)",
            endpoint,
            ", ".join(instrumented) or "none",
        )
        return provider
    except Exception as exc:  # noqa: BLE001 - fail-open seam
        logger.warning("OTLP trace wiring failed: %s", exc)
        return None


def shutdown_otlp_tracing() -> None:
    """Flush/shutdown the OTLP trace provider.

    Idempotent and safe to call when nothing was ever wired.
    """
    global _otlp_trace_provider
    provider = _otlp_trace_provider
    _otlp_trace_provider = None
    if provider is None:
        return
    try:
        provider.force_flush()
        provider.shutdown()
    except Exception as exc:  # noqa: BLE001 - teardown must never break shutdown
        logger.warning("OTLP trace provider shutdown failed: %s", exc)


def _wire_http_instruments() -> None:
    """Create the RED instruments once the meter provider is set.

    ``http.server.request.duration`` / ``http.server.requests`` follow the OTel
    HTTP semantic conventions. Instrument *names* are stable across restarts so
    the sink sees one time series per route, not one per process.
    """
    global _http_server_requests, _http_server_duration
    from opentelemetry import metrics as metrics_api

    meter = metrics_api.get_meter("civicpulse.http", version=settings.VERSION)
    _http_server_requests = meter.create_counter(
        "http.server.requests",
        unit="{request}",
        description="Total inbound HTTP requests handled.",
    )
    _http_server_duration = meter.create_histogram(
        "http.server.request.duration",
        unit="s",
        description="Inbound HTTP request duration in seconds.",
    )


def setup_otlp_metrics() -> Any | None:
    """Wire OTLP metric export (Layer 1 -> Layer 2).

    Env-gated exactly like logs and traces; the app pushes RED metrics on the
    same OTLP/HTTP path instead of exposing a Prometheus scrape endpoint, so a
    single vendor-neutral pipeline carries all three signals. Returns the
    provider, or ``None`` when disabled/unconfigured/missing extras (fail-open).
    """
    global _otlp_metrics_provider
    if _otlp_metrics_provider is not None:
        return _otlp_metrics_provider
    if not settings.NEW_RELIC_ENABLED:
        return None
    endpoint = _otlp_metrics_endpoint()
    if endpoint is None:
        return None
    try:
        from opentelemetry import metrics as metrics_api
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, timeout=10, headers=_otlp_headers()),
            export_interval_millis=settings.NEW_RELIC_EXPORT_INTERVAL_SECONDS * 1000,
        )
        provider = MeterProvider(resource=_service_resource(), metric_readers=[reader])
        metrics_api.set_meter_provider(provider)
        _otlp_metrics_provider = provider
        _wire_http_instruments()
        logger.info("OTLP metric export wired to %s", endpoint)
        return provider
    except Exception as exc:  # noqa: BLE001 - fail-open seam
        logger.warning("OTLP metric wiring failed: %s", exc)
        return None


def record_http_request(method: str, route: str, status_code: int, duration_seconds: float) -> None:
    """Record one inbound request on the RED instruments.

    A no-op until :func:`setup_otlp_metrics` has run (the OTel API returns a
    non-recording meter otherwise), so an unconfigured app pays nothing. The
    ``route`` is the matched route *template* (e.g. ``/api/v1/issues/{issue_id}``)
    rather than the raw path, so path parameters cannot explode cardinality.
    """
    if _http_server_requests is None or _http_server_duration is None:
        return
    attributes = {
        "http.request.method": method,
        "http.route": route,
        "http.response.status_code": status_code,
    }
    _http_server_requests.add(1, attributes)
    _http_server_duration.record(duration_seconds, attributes)


def shutdown_otlp_metrics() -> None:
    """Flush/shutdown the OTLP metric provider.

    Idempotent and safe to call when nothing was ever wired.
    """
    global _otlp_metrics_provider, _http_server_requests, _http_server_duration
    provider = _otlp_metrics_provider
    _otlp_metrics_provider = None
    _http_server_requests = None
    _http_server_duration = None
    if provider is None:
        return
    try:
        provider.force_flush()
        provider.shutdown()
    except Exception as exc:  # noqa: BLE001 - teardown must never break shutdown
        logger.warning("OTLP metric provider shutdown failed: %s", exc)
