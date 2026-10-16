"""Layer-1 -> Layer-2 observability behavior.

Covers the 3-layer OTLP architecture (ADR-0001, extended by ADR-0007):

* All three signals — logs, traces and metrics — are exported over OTLP, gated
  by ``NEW_RELIC_ENABLED`` and fail-open when the optional ``[observability]``
  extras are absent. An unconfigured or broken export must never break the app.
* There is no Prometheus ``/metrics`` scrape path (see
  ``test_metrics_scrape_endpoint_removed.py``).
* The receiver handshake (ADR-0008): the ``Authorization: Basic`` header the app
  sends must agree with what the collector's basicauth-gated receiver demands.
* Opt-in error tracking: Sentry is created only when ``SENTRY_DSN`` is set, and
  fails open when the optional sdk is not installed.

The collector-side half of that handshake (the receiver requiring the same
credential) lives in ``test_otel_collector_config.py``.
"""
from __future__ import annotations

import logging
import sys
import types

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


# ─────────────── OTLP receiver basic auth (the Authorization header) ────────
#
# The collector's OTLP receiver is basicauth-gated on a public host (see
# docker/otel-collector-config.yaml). These pin the handshake: an app that sends
# nothing while the receiver demands a credential would be a silent, permanent
# empty sink, and — the inverse — sending a half-built credential guarantees the
# same outcome, so both halves are asserted explicitly.


def test_auth_header_absent_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OTLP_AUTH_USER", "")
    monkeypatch.setattr(settings, "OTLP_AUTH_PASSWORD", "")
    # Unauthenticated receiver (the historical setup): send nothing extra.
    assert observability.otlp_auth_headers() is None


def test_auth_header_requires_a_complete_pair(monkeypatch) -> None:
    # A lone user or a lone password is a half-finished configuration. Sending
    # it would attempt a credential the collector is guaranteed to reject, so
    # it is treated as "no credentials" rather than a broken attempt.
    monkeypatch.setattr(settings, "OTLP_AUTH_USER", "civicpulse")
    monkeypatch.setattr(settings, "OTLP_AUTH_PASSWORD", "")
    assert observability.otlp_auth_headers() is None

    monkeypatch.setattr(settings, "OTLP_AUTH_USER", "")
    monkeypatch.setattr(settings, "OTLP_AUTH_PASSWORD", "civicpulse")
    assert observability.otlp_auth_headers() is None


def test_auth_header_is_standard_basic(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OTLP_AUTH_USER", "civicpulse")
    monkeypatch.setattr(settings, "OTLP_AUTH_PASSWORD", "civicpulse")
    # Asserted as a literal, not recomputed: recomputing base64 in the test
    # would make it tautological, and this string is exactly what the collector
    # parses out of htpasswd inline "civicpulse:civicpulse".
    assert observability.otlp_auth_headers() == {
        "Authorization": "Basic Y2l2aWNwdWxzZTpjaXZpY3B1bHNl"
    }


def test_otlp_headers_combine_auth_and_extra(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OTLP_AUTH_USER", "alice")
    monkeypatch.setattr(settings, "OTLP_AUTH_PASSWORD", "s3cr3t")
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_HEADERS", {"x-tenant": "acme"})
    assert observability._otlp_headers() == {
        "Authorization": "Basic YWxpY2U6czNjcjN0",
        "x-tenant": "acme",
    }


def test_otlp_headers_extra_wins_on_collision(monkeypatch) -> None:
    # NEW_RELIC_OTLP_HEADERS is the explicit escape hatch, so a deliberate value
    # there overrides the derived Basic header rather than silently losing.
    monkeypatch.setattr(settings, "OTLP_AUTH_USER", "alice")
    monkeypatch.setattr(settings, "OTLP_AUTH_PASSWORD", "s3cr3t")
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_HEADERS", {"Authorization": "Bearer other"})
    assert observability._otlp_headers() == {"Authorization": "Bearer other"}


def test_otlp_headers_none_when_nothing_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OTLP_AUTH_USER", "")
    monkeypatch.setattr(settings, "OTLP_AUTH_PASSWORD", "")
    monkeypatch.setattr(settings, "NEW_RELIC_OTLP_HEADERS", {})
    assert observability._otlp_headers() is None


# ──────────────────────────── Sentry (opt-in errors) ─────────────────────────


def test_setup_sentry_is_a_noop_without_a_dsn(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SENTRY_DSN", "")
    monkeypatch.setattr(observability, "_sentry_initialized", False)
    # The default everywhere (local, CI, tests): no DSN. Must not even try to
    # import the SDK, must not raise, and must leave the guard unflipped so a
    # later explicit configuration still works.
    assert observability.setup_sentry() is False
    assert observability._sentry_initialized is False


def test_setup_sentry_wires_the_sdk_when_a_dsn_is_set(monkeypatch) -> None:
    """Positive path with a stubbed module, so this runs in CI too.

    The real sentry-sdk lives in the optional [observability] extra and is
    absent from the default environment; substituting a recording stub keeps the
    contract under test (what is handed to ``init``, and how often) without
    installing the package or starting a background sender inside the suite.
    """
    calls: list[dict[str, object]] = []
    monkeypatch.setitem(sys.modules, "sentry_sdk", types.SimpleNamespace(init=lambda **kw: calls.append(kw)))
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.0)
    monkeypatch.setattr(observability, "_sentry_initialized", False)
    try:
        assert observability.setup_sentry() is True
        # A re-entered startup must not install a second client.
        assert observability.setup_sentry() is True
    finally:
        monkeypatch.setattr(observability, "_sentry_initialized", False)

    assert len(calls) == 1, "the client must be initialised exactly once"
    options = calls[0]
    assert options["dsn"] == "https://public@example.invalid/1"
    assert options["environment"] == "test"
    assert options["release"] == settings.VERSION
    # Errors only: traces already travel over OTLP, so Sentry must not be a
    # second, competing trace pipeline.
    assert options["traces_sample_rate"] == 0.0
    # No request bodies, cookies or identifiers in events.
    assert options["send_default_pii"] is False


def test_setup_sentry_fails_open_when_the_sdk_is_missing(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setattr(observability, "_sentry_initialized", False)
    # A DSN without the [observability] extra installed: one warning, then the
    # service carries on. An optional error reporter must never be the reason
    # the app fails to boot — the same fail-open rule the OTLP seam follows.
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    with caplog.at_level(logging.WARNING, logger="civicpulse"):
        assert observability.setup_sentry() is False
    assert "Sentry init failed" in caplog.text
    assert observability._sentry_initialized is False


def test_setup_sentry_is_idempotent_when_already_wired(monkeypatch) -> None:
    monkeypatch.setattr(observability, "_sentry_initialized", True)
    # Short-circuits before even looking at the DSN.
    assert observability.setup_sentry() is True
