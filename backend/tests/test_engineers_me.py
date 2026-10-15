"""Tests for ``GET /api/v1/engineers/me``.

The frontend calls this to decide whether to offer the engineer-only
"resolve with photo" flow, instead of scanning the full engineers list (which
may be admin-scoped). The endpoint must return the caller's own profile and a
404 when they do not have one.
"""
from __future__ import annotations

import pytest

from src.core.security import create_access_token


async def _seed_user(user_id: int, email: str, role: str) -> dict:
    from src.core.database import AsyncSessionLocal
    from src.models.user import User, UserRole

    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=user_id,
                email=email,
                password_hash="unused",
                full_name="ME Test User",
                role=UserRole(role),
                is_active=True,
            )
        )
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    token = create_access_token({"sub": str(user_id), "role": role})
    return {"Authorization": f"Bearer {token}"}


async def _seed_engineer(user_id: int, ward_id: int = 1) -> None:
    from src.core.database import AsyncSessionLocal
    from src.models.engineer import Engineer

    async with AsyncSessionLocal() as session:
        session.add(
            Engineer(
                user_id=user_id,
                ward_id=ward_id,
                specialization="general",
                max_workload=10,
            )
        )
        try:
            await session.commit()
        except Exception:
            await session.rollback()


@pytest.mark.asyncio
async def test_engineers_me_returns_own_profile(client, db_engine) -> None:
    headers = await _seed_user(9101, "eng-me@civicpulse.com", "engineer")
    await _seed_engineer(9101, ward_id=7)

    res = await client.get("/api/v1/engineers/me", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == 9101
    assert body["ward_id"] == 7
    assert body["specialization"] == "general"


@pytest.mark.asyncio
async def test_engineers_me_404_without_profile(client, db_engine) -> None:
    # A field worker with no engineer profile gets a clean 404, which the
    # frontend treats as "no resolution flow".
    headers = await _seed_user(9102, "no-profile@civicpulse.com", "field_worker")

    res = await client.get("/api/v1/engineers/me", headers=headers)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_engineers_me_requires_auth(client) -> None:
    res = await client.get("/api/v1/engineers/me")
    assert res.status_code in (401, 403)
