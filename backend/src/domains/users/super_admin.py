"""Startup preflight for the single-super-admin invariant.

The database partial unique index (migration 012) makes a *second* super admin
impossible, but it cannot guarantee that one *exists* — a fresh database before
bootstrap, or a demotion performed outside the app, can leave zero. This check
runs once at startup and emits a CRITICAL diagnostic when the invariant is not
met so an operator can fix it before the console is needed.

It is deliberately diagnostic only: an observability or bootstrap gap must not
restart-loop an otherwise healthy API fleet.
"""

from __future__ import annotations

import logging
from typing import TypedDict

logger = logging.getLogger("civicpulse")


class SuperAdminStatus(TypedDict):
    status: str
    count: int | None
    super_admin_id: int | None
    detail: str | None


_UNKNOWN: SuperAdminStatus = {
    "status": "unknown",
    "count": None,
    "super_admin_id": None,
    "detail": "not checked yet",
}
_last_status: SuperAdminStatus = _UNKNOWN.copy()


def get_super_admin_status() -> SuperAdminStatus:
    """Return the result of the most recent startup preflight."""
    return _last_status.copy()


async def verify_super_admin_invariant() -> SuperAdminStatus:
    """Count super admins and log the invariant result.

    Returns ``{"status": "ok"|"missing"|"ambiguous"|"unknown", "count": ...,
    "super_admin_id": ...}``. A store failure is reported as ``unknown`` rather
    than crashing the process — readiness already reflects database health.
    """
    global _last_status

    from sqlalchemy import select

    from src.core.database import AsyncSessionLocal
    from src.domains.users.models.user import User, UserRole

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User.id).where(User.role == UserRole.super_admin))
            ids = [row[0] for row in result.all()]
    except Exception as exc:
        _last_status = {**_UNKNOWN, "detail": f"database check failed: {type(exc).__name__}"}
        logger.error("super_admin preflight could not query the database: %s", exc)
        return get_super_admin_status()

    if len(ids) == 1:
        _last_status = {"status": "ok", "count": 1, "super_admin_id": ids[0], "detail": None}
        logger.info("super_admin invariant OK (user id=%s)", ids[0])
    elif not ids:
        _last_status = {
            "status": "missing",
            "count": 0,
            "super_admin_id": None,
            "detail": "No super admin exists; run scripts/create_admin.py with ADMIN_ROLE=super_admin.",
        }
        logger.critical(
            "super_admin invariant VIOLATED: no super admin exists. "
            "Run scripts/create_admin.py with ADMIN_ROLE=super_admin before using the admin console."
        )
    else:
        _last_status = {
            "status": "ambiguous",
            "count": len(ids),
            "super_admin_id": None,
            "detail": f"Multiple super admins (ids {ids}); demote all but one.",
        }
        logger.critical("super_admin invariant VIOLATED: %d super admins found (ids %s)", len(ids), ids)

    return get_super_admin_status()
