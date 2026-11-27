"""Browser error intake.

The browser has no safe place to put a vendor ingest key, and letting it post
straight to New Relic would expose that key to every visitor. Instead the Next.js
BFF forwards a small, allowlisted error report here, and this endpoint writes it
through the same structured logging pipeline (and therefore the same OTLP
export) as backend errors.

The route is unauthenticated by design — visitors who are not signed in still
hit error boundaries — so it accepts only short, scrubbed fields. The global
rate-limit and body-size middleware bound abuse; nothing from the browser is
trusted enough to be logged verbatim.
"""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.log_utils import get_logger

router = APIRouter(prefix="/observability", tags=["Observability"])

logger = get_logger("frontend")

_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|passwd|authorization|cookie)"
    r"([\"']?\s*[:=]\s*[\"']?)([^\s\"',}&]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{8,}")


def _scrub_text(value: str | None, limit: int) -> str | None:
    """Remove obvious credentials and bound the size of browser-supplied text."""
    if not value:
        return None
    cleaned = _BEARER_PATTERN.sub("Bearer ***REDACTED***", value)
    cleaned = _CREDENTIAL_PATTERN.sub(r"\1\2***REDACTED***", cleaned)
    cleaned = cleaned.split("\n", 1)[0][:limit]
    return cleaned or None


def _scrub_path(value: str | None) -> str | None:
    """Keep the path only — query strings commonly carry one-time codes."""
    if not value:
        return None
    return value.split("?", 1)[0].split("#", 1)[0][:300] or None


class ClientErrorReport(BaseModel):
    event_type: Literal["react_error", "api_error", "unhandled_rejection", "window_error"] = "react_error"
    message: str = Field(min_length=1, max_length=2_000)
    error_name: str | None = Field(default=None, max_length=200)
    path: str | None = Field(default=None, max_length=1_000)
    api_path: str | None = Field(default=None, max_length=1_000)
    method: str | None = Field(default=None, max_length=10)
    status_code: int | None = Field(default=None, ge=100, le=599)
    correlation_id: str | None = Field(default=None, max_length=64)
    stack: str | None = Field(default=None, max_length=20_000)
    timestamp: str | None = Field(default=None, max_length=40)
    digest: str | None = Field(default=None, max_length=64)


@router.post("/client-errors", status_code=202)
async def record_client_error(report: ClientErrorReport) -> dict[str, str]:
    """Emit one structured `frontend_error` event into the shared OTLP pipeline."""
    logger.error(
        "Frontend error: %s",
        _scrub_text(report.message, 1_000) or "unknown error",
        extra={
            "event_type": "frontend_error",
            "frontend_event_type": report.event_type,
            "error_name": _scrub_text(report.error_name, 200),
            "frontend_path": _scrub_path(report.path),
            "api_path": _scrub_path(report.api_path),
            "http_method": _scrub_text(report.method, 10),
            "http_status_code": report.status_code,
            "correlation_id": _scrub_text(report.correlation_id, 64),
            "error_stack": _scrub_text(report.stack, 4_000),
            "client_timestamp": _scrub_text(report.timestamp, 40),
            "error_digest": _scrub_text(report.digest, 64),
        },
    )
    return {"status": "accepted"}
