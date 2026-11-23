"""Shared audit-event emitter.

Auth routes used to build the Redis hot-list entry and the durable Mongo
document inline. Moving that logic here gives every caller the same redaction
policy and makes the "durable" half genuinely best-effort: an Atlas hiccup must
never turn a successful login into a 500.

Nothing written here contains a raw credential. Bearer tokens, refresh tokens,
OAuth state/nonce values and passwords are replaced before either sink sees the
payload.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping

logger = logging.getLogger("civicpulse")

_REDACTED = "[REDACTED]"
_MAX_STRING_LENGTH = 512

# Key-based redaction, deliberately broad: a new handler that dumps its request
# body into ``details`` should not have to remember this list. Exact matches
# cover short protocol names that would otherwise be too aggressive as
# substrings ("state" is fine, "status" is not).
_SENSITIVE_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "passwd",
    "authorization",
    "cookie",
    "code_verifier",
    "api_key",
    "private_key",
)
_SENSITIVE_EXACT = frozenset(
    {
        "code",
        "handoff",
        "oauth_state",
        "state",
        "nonce",
        "session_active",
        "cv",
    }
)


def _is_sensitive(key: Any) -> bool:
    name = str(key).lower()
    return name in _SENSITIVE_EXACT or any(part in name for part in _SENSITIVE_SUBSTRINGS)


def redact_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a JSON-safe copy with credential-like values removed.

    Nested dicts/lists are walked too; a handler that logs ``{"profile": {...}}``
    is just as capable of leaking a token as one that logs it at the top level.
    Long strings are truncated so a hostile user-agent cannot bloat the audit
    collection.
    """
    if not metadata:
        return {}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if _is_sensitive(key):
            clean[str(key)] = _REDACTED
        elif isinstance(value, Mapping):
            clean[str(key)] = redact_metadata(value)
        elif isinstance(value, (list, tuple)):
            clean[str(key)] = [redact_metadata({"v": item})["v"] for item in value]
        elif isinstance(value, str) and len(value) > _MAX_STRING_LENGTH:
            clean[str(key)] = value[:_MAX_STRING_LENGTH] + "…"
        else:
            clean[str(key)] = value
    return clean


def mask_ip(ip: str | None) -> str | None:
    """Admin listing keeps enough of an IP to investigate, not full PII."""
    if not ip:
        return None
    if "." in ip:
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.[redacted].{parts[-1]}" if len(parts) == 4 else "[redacted]"
    if ":" in ip:
        return ":".join(ip.split(":")[:2]) + "::[redacted]"
    return "[redacted]"


async def emit_audit_event(
    action: str,
    *,
    user_id: int | str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    details: Mapping[str, Any] | None = None,
    status: str = "success",
) -> dict[str, Any]:
    """Write one redacted event to the hot list and the durable store.

    Both writes fail open. The HTTP handler has already succeeded by the time
    this runs, so losing telemetry must not rewrite that outcome as a failure.
    """
    timestamp = datetime.now(timezone.utc)
    safe_details = redact_metadata(details)
    event: dict[str, Any] = {
        "action": action,
        "user_id": user_id,
        "ip": ip or "unknown",
        "user_agent": user_agent,
        "status": status,
        "details": safe_details,
        "timestamp": timestamp.isoformat(),
    }

    try:
        from src.core.redis import redis_client

        await redis_client.lpush("auth:audit", json.dumps(event, default=str))
        await redis_client.ltrim("auth:audit", 0, 999)
    except Exception as exc:  # nosec B110 - audit logging is best-effort
        logger.warning("audit: hot-list write failed for %s: %s", action, exc)

    try:
        from src.documents.audit_log import AuditLogDocument

        uid: int | None = None
        if user_id is not None:
            try:
                uid = int(user_id)
            except (TypeError, ValueError):
                uid = None
        await AuditLogDocument(
            action=action,
            user_id=uid,
            resource_type="auth",
            resource_id=str(user_id) if user_id is not None else None,
            status=status,
            metadata={"ip": ip or "unknown", "user_agent": user_agent, **safe_details},
            timestamp=timestamp,
        ).insert()
    except Exception as exc:  # nosec B110 - durable audit is best-effort
        logger.warning("audit: durable write failed for %s: %s", action, exc)

    return event
