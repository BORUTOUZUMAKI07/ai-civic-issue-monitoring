"""Baseline response headers for every API response.

Applied as the outermost middleware so that *every* answer carries them —
including the 429 built by the rate limiter, the 401/403 built by RBAC, and
the 500 from the exception handler, none of which pass through the inner
middlewares where a response is assembled.

Deliberately three headers, and deliberately not a CSP: this API serves JSON
plus a handful of short-lived OAuth bounce pages whose inline script is the
mechanism, so a meaningful CSP would be either wrong or permissive theatre.
The Next.js side already ships a real CSP for the pages people actually see
(``frontend/next.config.ts``).

``setdefault`` is used so a handler that has a good reason to override one
of these can; nothing in the codebase currently does.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# nosniff: a response declared as JSON (or an uploaded photo served by
# /issues/media) must never be reinterpreted as script or HTML by the browser.
# DENY: nothing on this API is meant to be framed — framing is the classic
# clickjacking wrapper around state-changing forms.
# same-origin: the API is never legitimately reached from a page on another
# origin's referrer, so send nothing to leak the URL of a record to a third
# party.
_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in _BASE_HEADERS.items():
            response.headers.setdefault(name, value)
        return response
