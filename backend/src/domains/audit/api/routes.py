"""Admin-only audit investigation and compliance endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from src.domains.audit.service import AuditReportService
from src.domains.users.deps import get_current_active_user
from src.domains.users.models.user import User
from src.domains.users.rbac import require_admin
from src.shared.errors import BadRequestError

router = APIRouter(prefix="/admin/audit", tags=["Admin", "Audit"])


class AuditReportResponse(BaseModel):
    generated_at: str
    period_days: int
    degraded: bool
    summary: dict[str, Any]
    events_by_action: list[dict[str, Any]]
    events_by_day: list[dict[str, Any]]
    security_events: dict[str, Any]
    gdpr_lifecycle: dict[str, Any]
    controls: dict[str, Any]
    retention: dict[str, Any]


def _parse_datetime(value: str | None, label: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BadRequestError(f"Invalid {label} timestamp.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _filters(
    action: str | None,
    user_id: int | None,
    status: str | None,
    start: str | None,
    end: str | None,
) -> dict[str, Any]:
    parsed_start = _parse_datetime(start, "start")
    parsed_end = _parse_datetime(end, "end")
    if parsed_start and parsed_end and parsed_start > parsed_end:
        raise BadRequestError("start must not be after end.")
    return {
        "action": action,
        "user_id": user_id,
        "status": status,
        "start": parsed_start,
        "end": parsed_end,
    }


@router.get("/events")
async def list_audit_events(
    action: str | None = Query(None),
    user_id: int | None = Query(None),
    status: str | None = Query(None, pattern="^(success|failure)$"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    require_admin(user)
    return await AuditReportService().list_events(
        **_filters(action, user_id, status, start, end), skip=skip, limit=limit
    )


@router.get("/report", response_model=AuditReportResponse)
async def audit_report(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    require_admin(user)
    return await AuditReportService().build_report(days=days)


@router.get("/export.csv")
async def export_audit_events(
    action: str | None = Query(None),
    user_id: int | None = Query(None),
    status: str | None = Query(None, pattern="^(success|failure)$"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    user: User = Depends(get_current_active_user),
) -> Response:
    require_admin(user)
    content = await AuditReportService().export_csv(**_filters(action, user_id, status, start, end))
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="civicpulse-audit.csv"'},
    )
