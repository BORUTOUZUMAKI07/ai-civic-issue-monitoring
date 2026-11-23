"""Audit redaction, fail-open writes, and admin compliance reporting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from src.core.config import settings
from src.documents.audit_log import AuditLogDocument
from src.domains.audit.events import emit_audit_event, mask_ip, redact_metadata
from src.domains.audit.service import AuditReportService


@pytest_asyncio.fixture
async def audit_db():
    """Fresh in-memory Mongo with Beanie bound to the audit document only."""
    client = AsyncMongoMockClient()
    await init_beanie(database=client["audit_unit"], document_models=[AuditLogDocument])
    yield client
    await AuditLogDocument.delete_all()


def _doc(action, *, user_id=7, status="success", days_ago=1, metadata=None):
    return AuditLogDocument(
        action=action,
        user_id=user_id,
        resource_type="auth",
        resource_id=str(user_id) if user_id else None,
        status=status,
        metadata=metadata or {"ip": "203.0.113.42", "user_agent": "pytest"},
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def test_redact_metadata_walks_nested_structures() -> None:
    clean = redact_metadata(
        {
            "access_token": "jwt-secret",
            "state": "oauth-nonce",
            "profile": {"password": "hunter2", "refresh_token": "abc"},
            "attempts": [{"code_verifier": "pkce"}, "safe"],
            "long": "x" * 700,
            "outcome": "success",
        }
    )
    assert clean["access_token"] == "[REDACTED]"
    assert clean["state"] == "[REDACTED]"
    assert clean["profile"] == {"password": "[REDACTED]", "refresh_token": "[REDACTED]"}
    assert clean["attempts"] == [{"code_verifier": "[REDACTED]"}, "safe"]
    assert clean["long"].endswith("…") and len(clean["long"]) < 700
    assert clean["outcome"] == "success"


def test_mask_ip_keeps_investigation_value_without_full_pii() -> None:
    assert mask_ip("203.0.113.42") == "203.0.[redacted].42"
    assert mask_ip("2001:db8::1").startswith("2001:db8::")
    assert mask_ip(None) is None


@pytest.mark.asyncio
async def test_emit_audit_event_fails_open_when_both_sinks_are_down() -> None:
    with (
        patch("src.core.redis.redis_client.lpush", new=AsyncMock(side_effect=ConnectionError("down"))),
        patch("src.documents.audit_log.AuditLogDocument.insert", new=AsyncMock(side_effect=ConnectionError("down"))),
    ):
        event = await emit_audit_event(
            "login", user_id=7, ip="203.0.113.42", details={"access_token": "jwt-secret"}
        )
    assert event["action"] == "login"
    assert event["details"]["access_token"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_list_events_filters_and_masks_ips(audit_db) -> None:
    await _doc("login", user_id=7).insert()
    await _doc("login", user_id=8, status="failure").insert()
    await _doc("refresh", user_id=7).insert()

    service = AuditReportService()
    result = await service.list_events(action="login", status="success", user_id=7)
    assert result["degraded"] is False
    assert result["total"] == 1
    assert result["items"][0]["action"] == "login"
    assert result["items"][0]["ip"] == "203.0.[redacted].42"

    all_events = await service.list_events(skip=1, limit=1)
    assert all_events["total"] == 3
    assert len(all_events["items"]) == 1


@pytest.mark.asyncio
async def test_report_groups_security_gdpr_and_controls(audit_db) -> None:
    await _doc("login").insert()
    await _doc("refresh_reuse_detected", status="failure").insert()
    await _doc("account_export").insert()
    await _doc("account_deleted").insert()

    report = await AuditReportService().build_report(days=30)
    assert report["degraded"] is False
    assert report["summary"]["total_events"] == 4
    assert report["summary"]["failure_events"] == 1
    assert report["security_events"]["reuse_detected"] == 1
    assert report["security_events"]["failures"] == 1
    assert report["gdpr_lifecycle"]["by_action"] == {"account_export": 1, "account_deleted": 1}
    assert report["controls"]["refresh_reuse_grace_seconds"] == settings.REFRESH_REUSE_GRACE_SECONDS
    assert report["retention"]["policy_days"] == settings.AUDIT_LOG_RETENTION_DAYS
    assert report["retention"]["archive_collection"] == "archived_audit_logs"


@pytest.mark.asyncio
async def test_csv_export_masks_ip_and_redacts_metadata(audit_db) -> None:
    await _doc(
        "login",
        metadata={"ip": "203.0.113.42", "user_agent": "pytest", "authorization": "Bearer abc"},
    ).insert()
    csv_text = await AuditReportService().export_csv(action="login")
    assert "timestamp,action,user_id,status,ip" in csv_text
    assert "203.0.[redacted].42" in csv_text
    assert "203.0.113.42" not in csv_text
    assert "Bearer abc" not in csv_text
    assert '[REDACTED]' in csv_text


@pytest.mark.asyncio
async def test_audit_endpoints_are_admin_only(client, admin_headers, auth_headers, audit_db) -> None:
    await _doc("login").insert()

    denied = await client.get("/api/v1/admin/audit/events", headers=auth_headers)
    assert denied.status_code == 403

    events = await client.get("/api/v1/admin/audit/events", headers=admin_headers)
    assert events.status_code == 200
    assert events.json()["total"] == 1

    report = await client.get("/api/v1/admin/audit/report?days=7", headers=admin_headers)
    assert report.status_code == 200
    assert report.json()["period_days"] == 7

    exported = await client.get("/api/v1/admin/audit/export.csv", headers=admin_headers)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "login" in exported.text
