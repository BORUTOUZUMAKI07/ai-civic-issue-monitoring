"""Layer-1 -> Layer-2 observability behavior.

Covers the 3-layer New Relic architecture introduced for parity with the
nexus-ai root project:

* ``/metrics`` stays the in-process metric source of truth, but when
  ``METRICS_TOKEN`` is set the Layer-2 collector must present it as a Bearer
  token (an unauthenticated scrape gets ``401``).
* The OTLP log export (``src/core/observability.py``) is a strict no-op unless
  ``NEW_RELIC_ENABLED`` is set and fails open when the optional OTLP extras are
  absent — an unconfigured or broken export must never break logging.
"""
from __future__ import annotations

import logging

import pytest

from src.core import observability
from src.core.config import settings

try:  # the [observability] extras may not be installed (optional extra)
    import opentelemetry  # noqa: F401

    _OTEL_INSTALLED = True
except ImportError:
    _OTEL_INSTALLED = False


# ─────────────────────────── /metrics bearer gate ───────────────────────────


async def test_metrics_open_when_no_token(client) -> None:
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "http_request" in resp.text


async def test_metrics_requires_token_when_configured(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "METRICS_TOKEN", "sekrit")
    resp = await client.get("/metrics")
    assert resp.status_code == 401

    resp = await client.get("/metrics", headers={"Authorization": "Bearer sekrit"})
    assert resp.status_code == 200

    resp = await client.get("/metrics", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


async def test_metrics_token_scheme_must_be_bearer(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "METRICS_TOKEN", "sekrit")
    resp = await client.get("/metrics", headers={"Authorization": "Basic c2Vrcml0"})
    assert resp.status_code == 401


async def test_metrics_token_does_not_lock_other_paths(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "METRICS_TOKEN", "sekrit")
    resp = await client.get("/health")
    assert resp.status_code == 200


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