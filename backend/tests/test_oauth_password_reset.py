from __future__ import annotations

import pytest
from httpx import AsyncClient

from src.core.config import settings
from src.domains.auth.oauth import decode_oauth_state, encode_oauth_state, get_provider
from src.domains.auth.password_reset import create_password_reset_token, decode_password_reset_token
from src.errors import OAuthNotConfigured, OAuthStateInvalid, PasswordResetTokenInvalid


def test_oauth_state_round_trip() -> None:
    state = encode_oauth_state("google", "/issues")
    assert decode_oauth_state("google", state) == "/issues"


def test_oauth_state_rejects_foreign_redirect() -> None:
    state = encode_oauth_state("google", "https://evil.example.com")
    with pytest.raises(OAuthStateInvalid):
        decode_oauth_state("google", state)


def test_oauth_state_rejects_provider_mismatch() -> None:
    state = encode_oauth_state("google", "/dashboard")
    with pytest.raises(OAuthStateInvalid):
        decode_oauth_state("github", state)


def test_oauth_state_rejects_garbage() -> None:
    with pytest.raises(OAuthStateInvalid):
        decode_oauth_state("google", "not-a-token")


def test_get_provider_unknown_raises() -> None:
    with pytest.raises(OAuthNotConfigured):
        get_provider("twitter")


def test_password_reset_token_round_trip() -> None:
    token = create_password_reset_token(42)
    assert decode_password_reset_token(token) == 42


def test_password_reset_token_rejects_wrong_type() -> None:
    from src.core.security import create_access_token

    access = create_access_token({"sub": "42"})
    with pytest.raises(PasswordResetTokenInvalid):
        decode_password_reset_token(access)


def test_password_reset_token_rejects_garbage() -> None:
    with pytest.raises(PasswordResetTokenInvalid):
        decode_password_reset_token("garbage-token")


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_soft_success(client: AsyncClient) -> None:
    # For an unknown email we return soft success so account existence is not
    # revealed; SMTP is not even attempted here.
    old_host = settings.SMTP_HOST
    settings.SMTP_HOST = ""
    try:
        response = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "anyone@civicpulse.com"},
        )
        assert response.status_code == 200
    finally:
        settings.SMTP_HOST = old_host


@pytest.mark.asyncio
async def test_forgot_password_existing_user_smtp_failure(client: AsyncClient) -> None:
    # A registered user whose reset email cannot be delivered surfaces an error.
    from unittest.mock import patch

    from src.core.database import AsyncSessionLocal, engine
    from src.models.base import Base
    from src.models.user import User, UserRole

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=999,
                email="existing@civicpulse.com",
                password_hash="unused",
                full_name="Existing User",
                role=UserRole.field_worker,
                is_active=True,
            )
        )
        await session.commit()

    old_host = settings.SMTP_HOST
    settings.SMTP_HOST = "smtp.example.com"
    try:
        with patch("src.domains.auth.password_reset.send_email", return_value=False) as fake_send:
            response = await client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "existing@civicpulse.com"},
            )
        assert response.status_code == 400
        assert fake_send.called
    finally:
        settings.SMTP_HOST = old_host


@pytest.mark.asyncio
async def test_reset_password_invalid_token(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "invalid-token", "new_password": "NewPass123!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_oauth_providers_endpoint(client: AsyncClient) -> None:
    old_google_id = settings.GOOGLE_CLIENT_ID
    old_google_secret = settings.GOOGLE_CLIENT_SECRET
    old_github_id = settings.GITHUB_CLIENT_ID
    old_github_secret = settings.GITHUB_CLIENT_SECRET
    settings.GOOGLE_CLIENT_ID = "cid"
    settings.GOOGLE_CLIENT_SECRET = "csecret"
    settings.GITHUB_CLIENT_ID = ""
    settings.GITHUB_CLIENT_SECRET = ""
    try:
        response = await client.get("/api/v1/auth/oauth/providers")
        assert response.status_code == 200
        body = response.json()
        assert body == {"google": True, "github": False}
    finally:
        settings.GOOGLE_CLIENT_ID = old_google_id
        settings.GOOGLE_CLIENT_SECRET = old_google_secret
        settings.GITHUB_CLIENT_ID = old_github_id
        settings.GITHUB_CLIENT_SECRET = old_github_secret


@pytest.mark.asyncio
async def test_oauth_authorize_unconfigured_returns_error(client: AsyncClient) -> None:
    old_google_id = settings.GOOGLE_CLIENT_ID
    settings.GOOGLE_CLIENT_ID = ""
    try:
        response = await client.get("/api/v1/auth/oauth/google/authorize", follow_redirects=False)
        assert response.status_code == 400
    finally:
        settings.GOOGLE_CLIENT_ID = old_google_id


@pytest.mark.asyncio
async def test_oauth_authorize_redirects_to_provider(client: AsyncClient) -> None:
    old_google_id = settings.GOOGLE_CLIENT_ID
    old_google_secret = settings.GOOGLE_CLIENT_SECRET
    settings.GOOGLE_CLIENT_ID = "client-123"
    settings.GOOGLE_CLIENT_SECRET = "secret-abc"
    try:
        response = await client.get("/api/v1/auth/oauth/google/authorize", follow_redirects=False)
        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
        assert "client_id=client-123" in location
        assert "state=" in location
    finally:
        settings.GOOGLE_CLIENT_ID = old_google_id
        settings.GOOGLE_CLIENT_SECRET = old_google_secret