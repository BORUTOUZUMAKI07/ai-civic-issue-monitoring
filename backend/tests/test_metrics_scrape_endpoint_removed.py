"""The Prometheus scrape path is gone; metrics travel OTLP instead (ADR-0007).

A regression guard against silently re-introducing a second metric surface: the
app must serve **no** ``/metrics`` endpoint, while health stays intact. Metrics
are now pushed over OTLP (``OTelMetricsMiddleware`` +
``observability.setup_otlp_metrics``), which the gating tests in
``test_observability_3layer.py`` cover.
"""
from __future__ import annotations


async def test_metrics_endpoint_is_removed(client) -> None:
    resp = await client.get("/metrics")
    assert resp.status_code == 404


async def test_health_is_still_served(client) -> None:
    resp = await client.get("/health")
    assert resp.status_code in (200, 503)
    assert resp.json()["status"] in ("healthy", "unhealthy")
