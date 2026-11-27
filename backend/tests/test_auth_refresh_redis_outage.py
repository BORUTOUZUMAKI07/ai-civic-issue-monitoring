"""Security-critical Redis state must fail closed.

Refresh rotation, session revocation and one-time token consumption are security
boundaries. When Redis is unavailable the service must not mint a replacement
token, claim a logout succeeded, or accept a replayed reset/verification/2FA
challenge. Rate limiting and caches still fail open by design — this file pins
the opposite rule for the operations whose loss would enable an auth bypass.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.database import AsyncSessionLocal
from src.core.security import create_refresh_token
from src.core.security_store import SecurityStoreUnavailableError

_USER_ID = 9001


class _DeadRedis:
    """A Redis client whose every call raises, exactly as during an outage."""

    async def get(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def setex(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def set(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def eval(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def delete(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def sadd(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def expire(self, *args, **kwargs):
        raise ConnectionError("redis down")

    async def ping(self, *args, **kwargs):
        raise ConnectionError("redis down")


@pytest.fixture
def dead_redis():
    with patch("src.core.redis.redis_client", _DeadRedis()):
        yield


@pytest.mark.asyncio
async def test_refresh_refuses_to_mint_tokens_during_redis_outage(dead_redis, db_engine) -> None:
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
        with pytest.raises(SecurityStoreUnavailableError):
            await AuthService(session).refresh(token)


@pytest.mark.asyncio
async def test_logout_does_not_claim_success_during_redis_outage(dead_redis, db_engine) -> None:
    from src.core.security import create_access_token
    from src.domains.auth.services.auth_service import AuthService

    token = create_access_token({"sub": str(_USER_ID)})
    async with AsyncSessionLocal() as session:
        with pytest.raises(SecurityStoreUnavailableError):
            await AuthService(session).logout(None, token)


@pytest.mark.asyncio
async def test_reset_token_cannot_be_consumed_during_redis_outage(dead_redis, db_engine) -> None:
    from src.domains.auth.password_reset import create_password_reset_token, reset_password

    token = create_password_reset_token(_USER_ID)
    async with AsyncSessionLocal() as session:
        with pytest.raises(SecurityStoreUnavailableError):
            await reset_password(session, token, "NewPass123!")


@pytest.mark.asyncio
async def test_verification_token_cannot_be_consumed_during_redis_outage(dead_redis, db_engine) -> None:
    from src.domains.auth.email_verification import create_email_verification_token, verify_email_token

    token = create_email_verification_token(_USER_ID)
    async with AsyncSessionLocal() as session:
        with pytest.raises(SecurityStoreUnavailableError):
            await verify_email_token(session, token)


@pytest.mark.asyncio
async def test_revoking_all_sessions_fails_closed_during_redis_outage(dead_redis, db_engine) -> None:
    from src.domains.auth.password_reset import revoke_all_refresh_sessions

    with pytest.raises(SecurityStoreUnavailableError):
        await revoke_all_refresh_sessions(_USER_ID)
