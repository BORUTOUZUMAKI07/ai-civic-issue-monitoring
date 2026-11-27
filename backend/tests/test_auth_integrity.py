"""Purpose-scoped credentials and trust-boundary tests.

Tokens minted for one flow (password reset, email verification, WebSocket)
must never be usable as another. These tests exercise the decoders and the
WebSocket admission helper directly, without opening a socket.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest

from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.core.security import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    create_ws_ticket,
)
from src.domains.auth.email_verification import (
    create_email_verification_token,
    decode_email_verification_token,
)
from src.domains.auth.password_reset import (
    create_password_reset_token,
    decode_password_reset_token,
)
from src.domains.notifications.api.routes import authenticate_ws_token
from src.domains.users.models.user import User, UserRole
from src.shared.errors import EmailVerificationTokenInvalid, PasswordResetTokenInvalid

_WS_USER_ID = 95001
_WS_EMAIL = "ws-integrity@example.test"


async def _seed_ws_user(*, active: bool = True) -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.get(User, _WS_USER_ID)
        if existing is None:
            session.add(
                User(
                    id=_WS_USER_ID,
                    email=_WS_EMAIL,
                    password_hash="x",
                    full_name="WS Test",
                    role=UserRole.field_worker,
                    is_active=active,
                )
            )
        else:
            existing.is_active = active
        await session.commit()


async def _remove_ws_user() -> None:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, _WS_USER_ID)
        if user is not None:
            await session.delete(user)
            await session.commit()


def _foreign_token(*, purpose: str, issuer: str | None = None, audience: str | None = None) -> str:
    payload = {
        "sub": "1",
        "type": purpose,
        "jti": "foreign-jti",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        "iss": issuer or settings.JWT_ISSUER,
        "aud": audience or settings.JWT_AUDIENCE,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ── reset / verification JWTs ────────────────────────────────────────────────


def test_reset_token_is_purpose_and_audience_scoped() -> None:
    token = create_password_reset_token(7)
    assert decode_password_reset_token(token)[0] == 7

    with pytest.raises(PasswordResetTokenInvalid):
        decode_password_reset_token(_foreign_token(purpose="password_reset", issuer="attacker"))
    with pytest.raises(PasswordResetTokenInvalid):
        decode_password_reset_token(_foreign_token(purpose="password_reset", audience="attacker"))
    with pytest.raises(PasswordResetTokenInvalid):
        decode_password_reset_token(create_access_token({"sub": "7"}))


def test_verification_token_is_purpose_and_audience_scoped() -> None:
    token = create_email_verification_token(7)
    assert decode_email_verification_token(token)[0] == 7

    with pytest.raises(EmailVerificationTokenInvalid):
        decode_email_verification_token(_foreign_token(purpose="email_verify", issuer="attacker"))
    with pytest.raises(EmailVerificationTokenInvalid):
        decode_email_verification_token(_foreign_token(purpose="email_verify", audience="attacker"))
    with pytest.raises(EmailVerificationTokenInvalid):
        decode_email_verification_token(create_access_token({"sub": "7"}))


# ── WebSocket admission ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ws_accepts_only_ws_tickets_and_live_access_tokens(db_engine) -> None:
    await _seed_ws_user()
    try:
        async with AsyncSessionLocal() as session:
            assert await authenticate_ws_token(create_ws_ticket(_WS_USER_ID), session) == _WS_USER_ID
            assert (
                await authenticate_ws_token(
                    create_access_token({"sub": str(_WS_USER_ID), "role": "field_worker"}), session
                )
                == _WS_USER_ID
            )
            assert await authenticate_ws_token(create_refresh_token({"sub": str(_WS_USER_ID)}), session) is None
            assert await authenticate_ws_token(create_password_reset_token(_WS_USER_ID), session) is None
            assert await authenticate_ws_token(create_email_verification_token(_WS_USER_ID), session) is None
            assert await authenticate_ws_token("garbage", session) is None
    finally:
        await _remove_ws_user()


@pytest.mark.asyncio
async def test_ws_rejects_missing_inactive_and_revoked_callers(db_engine) -> None:
    async with AsyncSessionLocal() as session:
        assert await authenticate_ws_token(create_ws_ticket(999999), session) is None

    await _seed_ws_user(active=False)
    try:
        async with AsyncSessionLocal() as session:
            assert await authenticate_ws_token(create_ws_ticket(_WS_USER_ID), session) is None
    finally:
        await _remove_ws_user()

    await _seed_ws_user()
    jti = "revoked-ws-jti"
    await blacklist_token(jti, 60)
    try:
        token = create_access_token({"sub": str(_WS_USER_ID), "role": "field_worker"}, jti=jti)
        async with AsyncSessionLocal() as session:
            assert await authenticate_ws_token(token, session) is None
    finally:
        await _remove_ws_user()


# ── OAuth identity binding ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oauth_refuses_unverified_relink_to_another_subject() -> None:
    from src.domains.auth.oauth import login_with_provider
    from src.domains.users.models.user import User as UserModel
    from src.shared.errors import OAuthError

    candidate = UserModel(
        id=96001,
        email="relink@example.test",
        password_hash="unused",
        full_name="Existing",
        role=UserRole.field_worker,
        oauth_provider="google",
        oauth_sub="old-sub",
    )
    profile = {
        "provider": "google",
        "provider_id": "new-sub",
        "email": "relink@example.test",
        "verified": False,
        "name": "Existing",
    }

    class _Repo:
        async def get_by_email(self, email: str) -> UserModel:
            return candidate

    with patch("src.domains.auth.oauth.get_user_by_oauth_identity", return_value=None), patch(
        "src.domains.auth.oauth.UserRepository", return_value=_Repo()
    ):
        with pytest.raises(OAuthError, match="different provider identity"):
            await login_with_provider(object(), object(), profile)  # type: ignore[arg-type]


# ── admin request bodies ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_bodies_are_validated_at_the_boundary(client, admin_headers) -> None:
    bad_action = await client.post(
        "/api/v1/admin/review/1",
        json={"action": "explode"},
        headers=admin_headers,
    )
    assert bad_action.status_code == 422

    bad_role = await client.post(
        "/api/v1/admin/users/2/role",
        json={"action": "change_type", "new_type": "superuser"},
        headers=admin_headers,
    )
    assert bad_role.status_code == 422

    missing_role = await client.post(
        "/api/v1/admin/users/2/role",
        json={"action": "change_type"},
        headers=admin_headers,
    )
    assert missing_role.status_code == 422
