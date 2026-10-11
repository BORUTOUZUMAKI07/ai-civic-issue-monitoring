"""Bearer-token gate for the Prometheus ``/metrics`` endpoint.

In the 3-layer setup the Layer-2 OpenTelemetry collector scrapes ``/metrics``
over the network, so an unauthenticated endpoint would leak request
shape/latency to anyone who can reach the app. When ``METRICS_TOKEN`` is set,
the scraper must present ``Authorization: Bearer <token>``; when it is unset
(local dev, tests) the endpoint stays open.

Deliberately narrow: only ``/metrics`` is affected, and a missing/incorrect
token yields a plain ``401`` without leaking whether the path exists.
"""

from __future__ import annotations

import hmac

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from src.core.config import settings

_PROTECTED_PATH = "/metrics"


class MetricsAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        token = settings.METRICS_TOKEN
        if not token or request.url.path != _PROTECTED_PATH:
            return await call_next(request)

        scheme, _, credentials = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(credentials, token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing metrics token."},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)
