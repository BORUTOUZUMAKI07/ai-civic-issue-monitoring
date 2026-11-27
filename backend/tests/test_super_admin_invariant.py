"""The exactly-one-super-admin invariant is enforced in the database.

Application checks (UserService, create_admin.py) keep ordinary callers honest,
but a bootstrap rerun or a direct SQL write must not be able to create a second
super admin. These tests exercise the partial unique index on the same SQLite
schema the production Postgres migration creates, plus the startup preflight.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.core.database import AsyncSessionLocal
from src.domains.users.models.user import User, UserRole
from src.domains.users.super_admin import get_super_admin_status, verify_super_admin_invariant

_EMAIL = "invariant-super-admin@civicpulse.test"


@pytest.mark.asyncio
async def test_partial_index_rejects_a_second_super_admin(db_engine) -> None:
    async with AsyncSessionLocal() as session:
        first = User(
            email=_EMAIL,
            password_hash="unused",
            full_name="Invariant Test",
            role=UserRole.super_admin,
        )
        session.add(first)
        await session.commit()

        try:
            second = User(
                email="second-" + _EMAIL,
                password_hash="unused",
                full_name="Second Super",
                role=UserRole.super_admin,
            )
            session.add(second)
            with pytest.raises(Exception) as exc:
                await session.commit()
            assert "UNIQUE constraint failed" in str(exc.value) or "unique" in str(exc.value).lower()
            await session.rollback()
        finally:
            await session.delete(first)
            await session.commit()


@pytest.mark.asyncio
async def test_preflight_reports_missing_then_ok(db_engine) -> None:
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(select(User.id).where(User.role == UserRole.super_admin))
        ).scalars().all()
        assert not existing, "test DB must not already contain a super admin"

    missing = await verify_super_admin_invariant()
    assert missing == get_super_admin_status()
    assert missing["status"] == "missing"
    assert missing["count"] == 0

    async with AsyncSessionLocal() as session:
        user = User(
            email=_EMAIL,
            password_hash="unused",
            full_name="Invariant Test",
            role=UserRole.super_admin,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    try:
        ok = await verify_super_admin_invariant()
        assert ok["status"] == "ok"
        assert ok["count"] == 1
        assert ok["super_admin_id"] == user_id
    finally:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                await session.delete(user)
                await session.commit()
