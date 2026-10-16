"""Layer-1 -> Layer-2 observability behavior.

Covers the 3-layer OTLP architecture (ADR-0001, extended by ADR-0007):

* All three signals — logs, traces and metrics — are exported over OTLP, gated
  by ``NEW_RELIC_ENABLED`` and fail-open when the optional ``[observability]``
  extras are absent. An unconfigured or broken export must never break the app.
* There is no Prometheus ``/metrics`` scrape path (see
  ``test_metrics_scrape_endpoint_removed.py``).
"""
from __future__ import annotations

import logging

import pytest

from src.core import observability
from src.core.config import settings

try:  # the [observability] extras may not be installed (optional extra)
    import opentelemetry  # noqa: F401
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: F401

    _OTEL_INSTALLED = True
except ImportError:
    # The pixi default env ships the SDK transitively (langsmith/langchain)
    # but not the exporter — `import opentelemetry` alone is NOT sufficient.
    _OTEL_INSTALLED = False


# ──────────────────────── OTLP log export gating ───────────────────────────


def test_otlp_handler_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", False)
    assert observability.setup_otlp_log_handler() is None


def test_otlp_handler_noop_when_endpoint_unset(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", True)
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_ENDPOINT", "")
    try:
        assert observability.setup_otlp_log_handler() is None
    finally:
        observability.shutdown_otlp_log_handler()


@pytest.mark.skipif(_OTEL_INSTALLED, reason="OTLP extras installed; fail-open path is not exercised")
def test_otlp_handler_fails_open_without_extras(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", True)
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_ENDPOINT", "http://localhost:4318")
    with caplog.at_level(logging.WARNING, logger="civicpulse"):
        try:
            handler = observability.setup_otlp_log_handler()
        finally:
            observability.shutdown_otlp_log_handler()
    assert handler is None
    assert "OTLP log handler wiring failed" in caplog.text


def test_otlp_shutdown_is_idempotent() -> None:
    observability.shutdown_otlp_log_handler()
    observability.shutdown_otlp_log_handler()  # second call must not raise


# ──────────────────────── OTLP trace export gating ──────────────────────────


def test_otlp_tracing_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", False)
    assert observability.setup_otlp_tracing(object()) is None


def test_otlp_tracing_noop_when_endpoint_unset(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", True)
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_ENDPOINT", "")
    try:
        assert observability.setup_otlp_tracing(object()) is None
    finally:
        observability.shutdown_otlp_tracing()


@pytest.mark.skipif(_OTEL_INSTALLED, reason="OTLP extras installed; fail-open path is not exercised")
def test_otlp_tracing_fails_open_without_extras(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", True)
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_ENDPOINT", "http://localhost:4318")
    with caplog.at_level(logging.WARNING, logger="civicpulse"):
        try:
            provider = observability.setup_otlp_tracing(object())
        finally:
            observability.shutdown_otlp_tracing()
    assert provider is None
    assert "OTLP trace wiring failed" in caplog.text


@pytest.mark.skipif(not _OTEL_INSTALLED, reason="requires the [observability] extras")
def test_otlp_tracing_wires_provider_when_enabled(monkeypatch) -> None:
    """Positive path: provider is created and set globally when enabled.

    Runs only where the optional extras are installed (locally on demand), so
    CI — which installs the default pixi env without them — skips it. The `app`
    argument is a bare object: individual instrumentors fail open (logged), but
    the exporter pipeline must still come up.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", True)
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_ENDPOINT", "http://localhost:4318")
    try:
        provider = observability.setup_otlp_tracing(object())
        assert isinstance(provider, TracerProvider)
        assert isinstance(trace.get_tracer_provider(), TracerProvider)
    finally:
        observability.shutdown_otlp_tracing()


def test_otlp_tracing_shutdown_is_idempotent() -> None:
    observability.shutdown_otlp_tracing()
    observability.shutdown_otlp_tracing()  # second call must not raise


# ─────────────────────── OTLP metric export gating ──────────────────────────


def test_otlp_metrics_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", False)
    assert observability.setup_otlp_metrics() is None


def test_otlp_metrics_noop_when_endpoint_unset(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", True)
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_ENDPOINT", "")
    try:
        assert observability.setup_otlp_metrics() is None
    finally:
        observability.shutdown_otlp_metrics()


@pytest.mark.skipif(_OTEL_INSTALLED, reason="OTLP extras installed; fail-open path is not exercised")
def test_otlp_metrics_fails_open_without_extras(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", True)
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_ENDPOINT", "http://localhost:4318")
    with caplog.at_level(logging.WARNING, logger="civicpulse"):
        try:
            provider = observability.setup_otlp_metrics()
        finally:
            observability.shutdown_otlp_metrics()
    assert provider is None
    assert "OTLP metric wiring failed" in caplog.text


@pytest.mark.skipif(not _OTEL_INSTALLED, reason="requires the [observability] extras")
def test_otlp_metrics_wires_provider_when_enabled(monkeypatch) -> None:
    from opentelemetry.sdk.metrics import MeterProvider

    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", True)
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_ENDPOINT", "http://localhost:4318")
    try:
        provider = observability.setup_otlp_metrics()
        assert isinstance(provider, MeterProvider)
    finally:
        observability.shutdown_otlp_metrics()


def test_otlp_metrics_shutdown_is_idempotent() -> None:
    observability.shutdown_otlp_metrics()
    observability.shutdown_otlp_metrics()  # second call must not raise


def test_record_http_request_is_noop_when_unconfigured() -> None:
    # With no provider wired the OTel instruments are absent; recording must be
    # a silent no-op, never an exception on the request path.
    observability.shutdown_otlp_metrics()
    observability.record_http_request("GET", "/health", 200, 0.0123)
