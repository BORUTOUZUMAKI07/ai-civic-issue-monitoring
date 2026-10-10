"""The Prometheus scrape endpoint must exist and stay unthrottled.

New Relic remains the APM of record; ``/metrics`` is the additive,
vendor-neutral RED feed for a Prometheus scraper. The two things worth locking
down are that the endpoint is mounted at all and that the rate-limit middleware
does not treat a scrape as user traffic.
"""
from __future__ import annotations


async def test_metrics_endpoint_is_served(client) -> None:
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    # The instrumentator's default collectors expose the request counter and
    # latency histogram under the ``http_request*`` family.
    assert "http_request" in resp.text


async def test_metrics_is_not_rate_limited(client) -> None:
    # Repeat scrapes must never draw a 429; the middleware exempts /metrics.
    for _ in range(5):
        resp = await client.get("/metrics")
        assert resp.status_code == 200
