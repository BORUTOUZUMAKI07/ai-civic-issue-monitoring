"""Refresh must survive a Redis outage.

Redis backs refresh-token rotation and the post-replay lockout flag, but the
``/auth/refresh`` route only catches :class:`AppError`. Before this test's fix,
a Redis ``ConnectError`` propagated out of ``AuthService.refresh`` and every
session renewal returned a 500 — an instance that was otherwise serving traffic
correctly logged every user out. This pins the fail-open behaviour: with Redis
unreachable, refresh still mints a fresh access/refresh pair.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.database import AsyncSessionLocal
from src.core.security import create_refresh_token

_USER_ID = 9001


class _DeadRedis:
    """A Redis client whose every call raises, exactly as during an outage."""

    async def get(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def setex(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def eval(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def delete(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def ping(self, *args, **kwargs):
        raise ConnectionError("redis down")


@pytest.mark.asyncio
async def test_refresh_survives_redis_outage(db_engine) -> None:
    from src.domains.auth.services.auth_service import AuthService
    from src.domains.users.models.user import User, UserRole

    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=_USER_ID,
                email="redis-outage@example.test",
                password_hash="unused",
                full_name="Outage Tester",
                role=UserRole.field_worker,
                is_active=True,
            )
        )
        try:
            await session.commit()
        except Exception:
            # The session-scoped test DB may already hold this row.
            await session.rollback()

        token = create_refresh_token({"sub": str(_USER_ID)})

        with patch("src.domains.auth.services.auth_service.redis_client", _DeadRedis()):
            access_token, new_refresh_token = await AuthService(session).refresh(token)

    assert access_token
    assert new_refresh_token
    assert new_refresh_token != token
