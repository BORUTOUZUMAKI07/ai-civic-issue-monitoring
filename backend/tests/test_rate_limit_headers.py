"""Unit tests for the rate-limit middleware's response shaping.

The bucket arithmetic lives in Redis and is exercised end-to-end elsewhere; what
matters here is the contract clients actually observe — the ``X-RateLimit-*``
budget headers and the ``Retry-After`` on a 429 — plus the guarantee that the
health and metrics endpoints are exempt.
"""
from __future__ import annotations

from src.core.redis import RateLimitResult
from src.middleware.rate_limit import (
    _UNTHROTTLED_PATHS,
    _rate_limit_headers,
    _too_many_requests,
)


def _result(**overrides) -> RateLimitResult:
    base = {"allowed": True, "remaining": 7, "reset_seconds": 42, "limit": 100}
    base.update(overrides)
    return RateLimitResult(**base)


def test_headers_report_the_budget() -> None:
    headers = _rate_limit_headers(_result())
    assert headers == {
        "X-RateLimit-Limit": "100",
        "X-RateLimit-Remaining": "7",
        "X-RateLimit-Reset": "42",
    }


def test_platform_paths_are_never_throttled() -> None:
    # A scrape or probe denied on a busy host would blind monitoring precisely
    # when it is needed most, so these must stay exempt.
    assert "/health" in _UNTHROTTLED_PATHS
    assert "/metrics" in _UNTHROTTLED_PATHS


def test_too_many_requests_is_429_with_retry_after() -> None:
    response = _too_many_requests(_result(allowed=False, remaining=0, reset_seconds=17))
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "17"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-RateLimit-Limit"] == "100"
    # Body mirrors the app-wide error shape so clients parse it uniformly.
    import json

    assert json.loads(response.body)["error_code"] == "RATE_LIMITED"
