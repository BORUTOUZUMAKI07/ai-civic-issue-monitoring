"""Layer-1 -> Layer-2 OTLP log and trace export for New Relic (env-gated).

Every line the app logs, and every span the instrumentors record, is forwarded
to the Layer-2 OpenTelemetry collector over OTLP/HTTP
(``docker/otel-collector-config.yaml``, the ``otel-collector`` compose
service). The collector owns the New Relic ingest key and forwards everything
on, so the app never holds a vendor credential.

Deliberately fail-open, in keeping with the rest of the stack:

* Gated by ``NEW_RELIC_ENABLED``; unset, or with no ``NEW_RELIC_OTLP_ENDPOINT``,
  it is a strict no-op.
* When enabled but the optional ``[observability]`` extras are not installed it
  degrades to a logged warning, never an exception.
* Export problems never affect requests or logging -- a broken collector drops
  telemetry, not log lines.

``/metrics`` (Prometheus) remains the in-process metric source of truth and is
scraped by the collector; this module carries logs and traces.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

from src.core.config import settings

logger = logging.getLogger("civicpulse")

_otlp_handler: logging.Handler | None = None
_otlp_provider: Any = None
_otlp_trace_provider: Any = None


def _otlp_base_endpoint() -> str | None:
    """The collector's OTLP/HTTP base URL, or ``None`` when unconfigured."""
    base = (settings.NEW_RELIC_OTLP_ENDPOINT or "").strip().rstrip("/")
    return base or None


def _otlp_logs_endpoint() -> str | None:
    base = _otlp_base_endpoint()
    if base is None:
        return None
    return f"{base}/v1/logs"


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
        from opentelemetry.sdk.resources import Resource

        exporter = OTLPLogExporter(endpoint=endpoint, timeout=10)
        processor = BatchLogRecordProcessor(
            exporter,
            schedule_delay_millis=settings.NEW_RELIC_EXPORT_INTERVAL_SECONDS * 1000,
        )
        provider = LoggerProvider(
            resource=Resource.create(
                {
                    "service.name": settings.NEW_RELIC_APP_NAME or settings.PROJECT_NAME,
                    "deployment.environment": settings.ENVIRONMENT,
                }
            )
        )
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
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": settings.NEW_RELIC_APP_NAME or settings.PROJECT_NAME,
                    "deployment.environment": settings.ENVIRONMENT,
                }
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", timeout=10),
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
