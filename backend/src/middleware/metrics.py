"""Inbound HTTP RED metrics emitted over OTLP.

Replaces the Prometheus ``/metrics`` scrape path: the app now pushes the same
rate/errors/duration signal through the OTLP pipeline
(:mod:`src.core.observability`) that carries logs and traces, so one
vendor-neutral transport covers all three signals.

Written as a pure ASGI middleware rather than a ``BaseHTTPMiddleware`` so the
final scope is visible: Starlette's router sets ``scope["route"]`` while
handling the request, and after the inner app returns we can read it to label
the metric with the route *template* instead of the raw path. Labelling on the
raw path (with its IDs and slugs) is the classic way cardinality -- and the
metrics bill -- gets away from you at scale.
"""

from __future__ import annotations

import time
from typing import Any

from src.core import observability


def _route_template(scope: dict[str, Any]) -> str:
    """The matched route template, or a constant when nothing matched.

    Returning a constant for unmatched requests (404s, or a failure before
    routing) rather than the raw path guarantees an arbitrary URL cannot mint a
    new time series.
    """
    route = scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return str(path)
    return "unmatched"


class OTelMetricsMiddleware:
    """Record ``http.server.requests`` / ``http.server.request.duration`` per request."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_with_status(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            # Runs on success *and* on an unhandled exception, so a crashing
            # handler still shows up as a 5xx in the error-rate signal.
            observability.record_http_request(
                scope.get("method", "GET"),
                _route_template(scope),
                status_code,
                time.perf_counter() - start,
            )
