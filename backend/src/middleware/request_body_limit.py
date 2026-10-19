"""Refuse oversized request bodies before their parser ever sees them.

Two parsers in this app read a request body into memory, and neither has a
built-in ceiling:

* ``await request.json()`` — used by every JSON endpoint — accumulates the
  whole stream in memory. An anonymous ``POST /api/v1/auth/login`` carrying a
  1 GB body is therefore a pre-auth memory exhaustion primitive on its own.
* the multipart parser on the two upload routes spools a file part to a
  temporary file while parsing, so an oversized "photo" has already been
  written to disk before any handler-level size check could run.

Rejecting on the declared ``Content-Length`` here, ahead of routing and
parsing, closes both without adding a place that buffers large bodies itself.
It is deliberately a header check — O(1), no streaming rewrite — and the
route-level bounded read in ``src.shared.uploads`` remains the backstop for
clients that send no length (chunked) or lie about it.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.shared.uploads import MAX_JSON_BODY_BYTES, MAX_UPLOAD_BODY_BYTES, UPLOAD_FORM_PATHS

_BODIED_METHODS = frozenset({"POST", "PUT", "PATCH"})


def _rejection(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={"detail": detail, "error_code": "PAYLOAD_TOO_LARGE"},
    )


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in _BODIED_METHODS:
            return await call_next(request)

        raw_length = request.headers.get("content-length")
        # Only a well-formed length can be trusted to reject on; anything else
        # (absent, malformed — the chunked-encoding case) falls through to the
        # route, whose own bounded read still applies.
        if not raw_length or not raw_length.isdigit():
            return await call_next(request)

        declared = int(raw_length)
        if request.url.path in UPLOAD_FORM_PATHS:
            if declared > MAX_UPLOAD_BODY_BYTES:
                return _rejection(
                    f"Request body exceeds the {MAX_UPLOAD_BODY_BYTES // (1024 * 1024)}MB upload limit.",
                )
        elif declared > MAX_JSON_BODY_BYTES:
            return _rejection(
                f"Request body exceeds the {MAX_JSON_BODY_BYTES // (1024 * 1024)}MB limit.",
            )

        return await call_next(request)
