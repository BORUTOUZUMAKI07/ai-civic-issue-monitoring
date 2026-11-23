"""Compliance reporting over the durable audit trail.

The raw `AuditLogDocument` collection is an operational log; this service turns
it into the three artefacts an auditor actually asks for:

* a filtered event listing (investigation),
* a period report with security/GDPR groupings and the controls that were active
  when it was generated, and
* a CSV export with IP addresses masked and metadata re-redacted.

Mongo is a read-only dependency here. If it is unavailable the endpoints return
an empty result with a ``degraded`` flag rather than a 500 — the same fail-open
posture the emitter uses.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.config import settings
from src.documents.audit_log import AuditLogDocument
from src.domains.audit.events import mask_ip, redact_metadata

logger = logging.getLogger("civicpulse")

# Groupings are explicit rather than inferred from substrings: an auditor needs
# to know exactly which events count as "security-relevant", and adding a new
# action should be a reviewed decision.
SECURITY_ACTIONS = frozenset(
    {
        "login",
        "login_2fa_challenge",
        "oauth_login",
        "oauth_exchange",
        "2fa_verified",
        "2fa_enabled",
        "2fa_disabled",
        "2fa_recovery_regenerate",
        "refresh",
        "refresh_reuse_detected",
        "password_change",
        "password_reset",
        "session_revoked",
        "sessions_revoked_all",
        "logout",
    }
)
GDPR_ACTIONS = frozenset({"account_export", "account_deleted", "email_verified"})


def _iso(value: datetime | Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


class AuditReportService:
    """Read-only queries over `audit_logs`."""

    @staticmethod
    def _build_query(
        *,
        action: str | None = None,
        user_id: int | None = None,
        status: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Any:
        conditions = []
        if action:
            conditions.append(AuditLogDocument.action == action)
        if user_id is not None:
            conditions.append(AuditLogDocument.user_id == user_id)
        if status:
            conditions.append(AuditLogDocument.status == status)
        if start:
            conditions.append(AuditLogDocument.timestamp >= start)
        if end:
            conditions.append(AuditLogDocument.timestamp <= end)
        return AuditLogDocument.find(*conditions)

    @staticmethod
    def _serialize(doc: AuditLogDocument, *, mask: bool = False) -> dict[str, Any]:
        metadata = dict(doc.metadata or {})
        ip = metadata.pop("ip", None)
        return {
            "id": str(doc.id),
            "action": doc.action,
            "user_id": doc.user_id,
            "status": getattr(doc, "status", "success") or "success",
            "resource_type": doc.resource_type,
            "resource_id": doc.resource_id,
            "ip": mask_ip(ip) if mask else ip,
            "user_agent": metadata.pop("user_agent", None),
            "metadata": redact_metadata(metadata),
            "timestamp": _iso(doc.timestamp),
        }

    async def list_events(
        self,
        *,
        action: str | None = None,
        user_id: int | None = None,
        status: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        try:
            query = self._build_query(action=action, user_id=user_id, status=status, start=start, end=end)
            total = await query.count()
            docs = await query.sort("-timestamp").skip(skip).limit(limit).to_list()
            return {
                "items": [self._serialize(doc, mask=True) for doc in docs],
                "total": total,
                "degraded": False,
            }
        except Exception as exc:  # nosec B110 - Mongo is optional at read time
            logger.warning("audit: event listing unavailable: %s", exc)
            return {"items": [], "total": 0, "degraded": True}

    async def build_report(self, *, days: int = 30) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        available = True
        try:
            docs = await AuditLogDocument.find(AuditLogDocument.timestamp >= since).to_list()
        except Exception as exc:  # nosec B110 - Mongo is optional at read time
            logger.warning("audit: report unavailable: %s", exc)
            docs = []
            available = False

        by_action = Counter(doc.action for doc in docs)
        by_status = Counter(getattr(doc, "status", "success") or "success" for doc in docs)
        by_day = Counter(_iso(doc.timestamp)[:10] for doc in docs)
        security = [doc for doc in docs if doc.action in SECURITY_ACTIONS]
        gdpr = [doc for doc in docs if doc.action in GDPR_ACTIONS]
        timestamps = [_iso(doc.timestamp) for doc in docs]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            "degraded": not available,
            "summary": {
                "total_events": len(docs),
                "success_events": by_status.get("success", 0),
                "failure_events": by_status.get("failure", 0),
                "unique_users": len({doc.user_id for doc in docs if doc.user_id is not None}),
            },
            "events_by_action": [{"action": name, "count": count} for name, count in by_action.most_common()],
            "events_by_day": [{"date": day, "count": count} for day, count in sorted(by_day.items())],
            "security_events": {
                "total": len(security),
                "by_action": dict(Counter(doc.action for doc in security)),
                "reuse_detected": sum(1 for doc in security if doc.action == "refresh_reuse_detected"),
                "failures": sum(1 for doc in security if (getattr(doc, "status", "success") or "success") == "failure"),
            },
            "gdpr_lifecycle": {
                "total": len(gdpr),
                "by_action": dict(Counter(doc.action for doc in gdpr)),
            },
            "controls": {
                "refresh_reuse_grace_seconds": settings.REFRESH_REUSE_GRACE_SECONDS,
                "refresh_revoke_on_reuse": settings.REFRESH_REVOKE_ON_REUSE,
                "oauth_handoff_ttl_seconds": settings.OAUTH_HANDOFF_TTL_SECONDS,
                "cookie_secure": settings.COOKIE_SECURE,
                "audit_redaction": True,
            },
            "retention": {
                "policy_days": settings.AUDIT_LOG_RETENTION_DAYS,
                "archive_collection": "archived_audit_logs",
                "oldest_event_at": min(timestamps) if timestamps else None,
                "newest_event_at": max(timestamps) if timestamps else None,
            },
        }

    async def export_csv(
        self,
        *,
        action: str | None = None,
        user_id: int | None = None,
        status: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> str:
        """Return a bounded CSV snapshot. Max 10k rows keeps exports predictable."""
        try:
            docs = (
                await self._build_query(action=action, user_id=user_id, status=status, start=start, end=end)
                .sort("-timestamp")
                .limit(10_000)
                .to_list()
            )
        except Exception as exc:  # nosec B110 - Mongo is optional at read time
            logger.warning("audit: CSV export unavailable: %s", exc)
            docs = []

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "action", "user_id", "status", "ip", "resource_type", "resource_id", "metadata"])
        for doc in docs:
            row = self._serialize(doc, mask=True)
            writer.writerow(
                [
                    row["timestamp"],
                    row["action"],
                    row["user_id"] if row["user_id"] is not None else "",
                    row["status"],
                    row["ip"] or "",
                    row["resource_type"],
                    row["resource_id"] or "",
                    json.dumps(row["metadata"], default=str, sort_keys=True),
                ]
            )
        return output.getvalue()
