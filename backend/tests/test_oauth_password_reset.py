from __future__ import annotations

import re

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.core.config import settings
from src.domains.auth.oauth import (
    code_challenge,
    decode_oauth_bundle,
    decode_oauth_state,
    encode_oauth_state,
    get_provider,
)
from src.domains.auth.password_reset import create_password_reset_token, decode_password_reset_token
from src.shared.errors import OAuthError, OAuthNotConfigured, OAuthStateInvalid, PasswordResetTokenInvalid


def test_oauth_state_round_trip() -> None:
    state, verifier, nonce = encode_oauth_state("google", "/issues")
    assert decode_oauth_state("google", state) == "/issues"
    # The flow bundle must carry a per-initiation nonce and a PKCE verifier.
    assert nonce
    assert verifier
    assert len(verifier) >= 43  # RFC 7636 minimum verifier length
    assert code_challenge(verifier)
    bundle = decode_oauth_bundle("google", state)
    assert bundle["nonce"] == nonce
    assert bundle["code_verifier"] == verifier


def test_oauth_state_rejects_foreign_redirect() -> None:
    state, _verifier, _nonce = encode_oauth_state("google", "https://evil.example.com")
    with pytest.raises(OAuthStateInvalid):
        decode_oauth_state("google", state)


def test_oauth_state_rejects_provider_mismatch() -> None:
    state, _verifier, _nonce = encode_oauth_state("google", "/dashboard")
    with pytest.raises(OAuthStateInvalid):
        decode_oauth_state("github", state)


def test_oauth_state_rejects_garbage() -> None:
    with pytest.raises(OAuthStateInvalid):
        decode_oauth_state("google", "not-a-token")


def test_oauth_state_without_nonce_is_rejected() -> None:
    """State tokens without a nonce (pre-fix or hand-built) must fail closed so
    the browser-session binding can never be silently downgraded."""
    from datetime import datetime, timedelta, timezone

    from jose import jwt as jose_jwt

    legacy = jose_jwt.encode(
        {
            "provider": "google",
            "redirect": "/dashboard",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(OAuthStateInvalid):
        decode_oauth_state("google", legacy)


def test_get_provider_unknown_raises() -> None:
    with pytest.raises(OAuthNotConfigured):
        get_provider("twitter")


# ─────────────────────────────────────────────────────────────────────────────
# OAuth provider profile fetching (email verification)
# ─────────────────────────────────────────────────────────────────────────────


class _FakeResp:
    def __init__(self, payload, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class _FakeClient:
    """Queue-based httpx.AsyncClient stand-in; responses pop in call order."""

    def __init__(self, responses: list[_FakeResp]):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def post(self, url: str, **kwargs) -> _FakeResp:
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)

    async def get(self, url: str, **kwargs) -> _FakeResp:
        self.calls.append(("get", url, kwargs))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_fetch_user_github_requires_verified_email_from_user_emails() -> None:
    """/user's public `email` must be ignored; /user/emails (verified, primary
    preferred) is the only source of truth — mirroring url-shortner / nexus."""
    fake = _FakeClient(
        [
            _FakeResp({"access_token": "tok-1"}),  # token exchange
            _FakeResp({"id": 42, "login": "octo", "name": "Octo", "email": "public@example.com"}),  # /user
            _FakeResp(  # /user/emails — always consulted, never a fallback
                [
                    {"email": "secondary@example.com", "primary": False, "verified": False},
                    {"email": "primary@example.com", "primary": True, "verified": True},
                ]
            ),
        ]
    )
    with patch("src.domains.auth.oauth.httpx.AsyncClient", return_value=fake):
        profile = await get_provider("github").fetch_user(
            "code-1",
            "http://localhost:3000/api/proxy/auth/oauth/github/callback",
            code_verifier="cv-1",
        )

    assert profile["email"] == "primary@example.com"  # the public /user email is ignored
    assert profile["verified"] is True
    assert profile["provider_id"] == "42"
    # The PKCE verifier must be sent on the token exchange…
    assert fake.calls[0][0] == "post"
    assert fake.calls[0][2]["data"]["code_verifier"] == "cv-1"
    # …and /user/emails must be hit unconditionally.
    assert any(c[0] == "get" and c[1] == "https://api.github.com/user/emails" for c in fake.calls)


@pytest.mark.asyncio
async def test_fetch_user_github_without_verified_email_is_unverified() -> None:
    fake = _FakeClient(
        [
            _FakeResp({"access_token": "tok-1"}),
            _FakeResp({"id": 7, "login": "anon", "name": "Anon", "email": "fake@example.com"}),
            _FakeResp([{"email": "unverified@example.com", "primary": True, "verified": False}]),
        ]
    )
    with patch("src.domains.auth.oauth.httpx.AsyncClient", return_value=fake):
        profile = await get_provider("github").fetch_user(
            "code-1", "http://localhost:3000/auth/oauth/github/callback"
        )
    assert profile["verified"] is False
    # Never accept an unverified GitHub address as the account email.
    assert profile["email"] == ""


@pytest.mark.asyncio
async def test_fetch_user_google_surfaces_email_verified() -> None:
    fake = _FakeClient(
        [
            _FakeResp({"access_token": "tok-1"}),
            _FakeResp({"sub": "sub-99", "email": "g@example.com", "name": "G User", "email_verified": True}),
        ]
    )
    with patch("src.domains.auth.oauth.httpx.AsyncClient", return_value=fake):
        profile = await get_provider("google").fetch_user(
            "code-1", "http://localhost:3000/auth/oauth/google/callback", code_verifier="cv-2"
        )
    assert profile["verified"] is True
    assert profile["email"] == "g@example.com"
    assert fake.calls[0][2]["data"]["code_verifier"] == "cv-2"


@pytest.mark.asyncio
async def test_fetch_user_google_unverified_claim_is_false() -> None:
    fake = _FakeClient(
        [
            _FakeResp({"access_token": "tok-1"}),
            _FakeResp({"sub": "sub-100", "email": "g2@example.com", "email_verified": False}),
        ]
    )
    with patch("src.domains.auth.oauth.httpx.AsyncClient", return_value=fake):
        profile = await get_provider("google").fetch_user(
            "code-1", "http://localhost:3000/auth/oauth/google/callback"
        )
    assert profile["verified"] is False


# ─────────────────────────────────────────────────────────────────────────────
# login_with_provider rule 4 — never link into a password-protected account
# unless the provider has verified the email
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oauth_unverified_email_not_linked_into_password_account(db_engine) -> None:
    from src.core.database import AsyncSessionLocal
    from src.domains.auth.oauth import login_with_provider
    from src.domains.users.models.user import User, UserRole

    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=211,
                email="pw-protected@civicpulse.com",
                password_hash="hashed-password",
                full_name="Pw User",
                role=UserRole.field_worker,
                is_active=True,
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        with pytest.raises(OAuthError):
            await login_with_provider(
                session,
                get_provider("google"),
                {
                    "provider": "google",
                    "provider_id": "sub-211",
                    "email": "pw-protected@civicpulse.com",
                    "name": "Google User",
                    "verified": False,
                },
            )

    # The account must not have been re-bound to the provider identity.
    async with AsyncSessionLocal() as session:
        account = await session.get(User, 211)
        assert account.oauth_provider is None
        assert account.oauth_sub is None


@pytest.mark.asyncio
async def test_oauth_verified_email_linked_into_password_account(db_engine) -> None:
    from src.core.database import AsyncSessionLocal
    from src.domains.auth.oauth import login_with_provider
    from src.domains.users.models.user import User, UserRole

    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=212,
                email="link-me@civicpulse.com",
                password_hash="hashed-password",
                full_name="Link User",
                role=UserRole.field_worker,
                is_active=True,
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        user, access_token, refresh_token = await login_with_provider(
            session,
            get_provider("google"),
            {
                "provider": "google",
                "provider_id": "sub-212",
                "email": "link-me@civicpulse.com",
                "name": "Linked",
                "verified": True,
            },
        )
    assert user.id == 212
    assert user.oauth_provider == "google"
    assert user.oauth_sub == "sub-212"
    assert access_token and refresh_token


@pytest.mark.asyncio
async def test_oauth_same_provider_reauth_not_blocked(db_engine) -> None:
    """An OAuth-created account (unusable random hash + same-provider binding)
    re-authenticating must NOT trip rule 4 — that is re-auth, not takeover."""
    from src.core.database import AsyncSessionLocal
    from src.domains.auth.oauth import login_with_provider
    from src.domains.users.models.user import User, UserRole

    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=213,
                email="oauth-existing@civicpulse.com",
                password_hash="unusable-hash",
                full_name="OAuth User",
                role=UserRole.field_worker,
                is_active=True,
                oauth_provider="google",
                oauth_sub="sub-213",
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        user, _, _ = await login_with_provider(
            session,
            get_provider("google"),
            {
                "provider": "google",
                "provider_id": "sub-213",
                "email": "oauth-existing@civicpulse.com",
                "name": "OAuth User",
                "verified": False,
            },
        )
    assert user.id == 213


@pytest.mark.asyncio
async def test_oauth_new_account_created_without_existing_candidate(db_engine) -> None:
    from src.core.database import AsyncSessionLocal
    from src.domains.auth.oauth import login_with_provider
    from src.domains.users.models.user import User

    async with AsyncSessionLocal() as session:
        user, _, _ = await login_with_provider(
            session,
            get_provider("google"),
            {
                "provider": "google",
                "provider_id": "sub-214",
                "email": "brand-new@civicpulse.com",
                "name": "New User",
                "verified": False,
            },
        )
    assert user.id is not None
    assert user.oauth_provider == "google"
    assert user.oauth_sub == "sub-214"
    # Fresh accounts keep an unusable random password hash (never a real one):
    # the stored value is an Argon2 hash of a random secret, not plaintext.
    assert user.password_hash.startswith("$argon2")


# ─────────────────────────────────────────────────────────────────────────────
# Password reset
# ─────────────────────────────────────────────────────────────────────────────


def test_password_reset_token_round_trip() -> None:
    token = create_password_reset_token(42)
    user_id, jti = decode_password_reset_token(token)
    assert user_id == 42
    # Every token must carry a jti so it can be marked consumed after first use.
    assert jti


def test_password_reset_tokens_are_unique() -> None:
    # Two tokens for the same user must not share a jti, otherwise consuming
    # one would silently invalidate the other (or, worse, allow a replay).
    _, jti_a = decode_password_reset_token(create_password_reset_token(7))
    _, jti_b = decode_password_reset_token(create_password_reset_token(7))
    assert jti_a != jti_b


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
    # A known address whose mail cannot be delivered must look *identical* to
    # an unknown address. The earlier behaviour raised 400 here while returning
    # 200 for an unregistered address, which turned this endpoint into an
    # account-enumeration oracle: one request per address told an attacker
    # exactly which mailboxes exist.
    from unittest.mock import patch

    from src.core.database import AsyncSessionLocal, engine
    from src.models.base import Base
    from src.domains.users.models.user import User, UserRole

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
        assert response.status_code == 200
        assert response.json() == {
            "detail": "If that email is registered, a reset link has been sent."
        }
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
async def test_oauth_callback_sets_cookies_via_200_html(client: AsyncClient) -> None:
    """The callback must return a 200 page that carries the auth cookies (not a
    302), matching the reliable email/login cookie path through the proxy."""
    old_google_id = settings.GOOGLE_CLIENT_ID
    old_google_secret = settings.GOOGLE_CLIENT_SECRET
    old_frontend = settings.FRONTEND_URL
    settings.GOOGLE_CLIENT_ID = "client-123"
    settings.GOOGLE_CLIENT_SECRET = "secret-abc"
    settings.FRONTEND_URL = "http://localhost:3000"
    state, _verifier, nonce = encode_oauth_state("google", "/dashboard")
    try:
        with patch(
            "src.domains.auth.oauth.OAuthProvider.fetch_user",
            new=AsyncMock(
                return_value={
                    "provider": "google",
                    "provider_id": "12345",
                    "email": "oauth@civicpulse.com",
                    "name": "OAuth User",
                    "verified": True,
                }
            ),
        ):
            response = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=fake&state={state}",
                cookies={"oauth_state": nonce},
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert response.headers.get("cache-control") == "no-store"
        body = response.text
        assert "http://localhost:3000/dashboard" in body
        set_cookie = "; ".join(response.headers.get_list("set-cookie", []))
        assert "access_token=" in set_cookie
        assert "refresh_token=" in set_cookie
        assert "session_active=1" in set_cookie
        # The one-shot session-binding cookie is consumed on success.
        assert "oauth_state=" in set_cookie and "Max-Age=0" in set_cookie
    finally:
        settings.GOOGLE_CLIENT_ID = old_google_id
        settings.GOOGLE_CLIENT_SECRET = old_google_secret
        settings.FRONTEND_URL = old_frontend


@pytest.mark.asyncio
async def test_oauth_callback_rejects_missing_state_cookie(client: AsyncClient) -> None:
    """Login-CSRF: a state harvested from an attacker's own authorize must fail
    in the victim's browser, which holds no oauth_state cookie."""
    old_google_id = settings.GOOGLE_CLIENT_ID
    old_google_secret = settings.GOOGLE_CLIENT_SECRET
    settings.GOOGLE_CLIENT_ID = "client-123"
    settings.GOOGLE_CLIENT_SECRET = "secret-abc"
    state, _verifier, _nonce = encode_oauth_state("google", "/dashboard")
    try:
        response = await client.get(
            f"/api/v1/auth/oauth/google/callback?code=attacker-code&state={state}",
            follow_redirects=False,
        )
        assert response.status_code == 400
    finally:
        settings.GOOGLE_CLIENT_ID = old_google_id
        settings.GOOGLE_CLIENT_SECRET = old_google_secret


@pytest.mark.asyncio
async def test_oauth_callback_rejects_mismatched_state_cookie(client: AsyncClient) -> None:
    old_google_id = settings.GOOGLE_CLIENT_ID
    old_google_secret = settings.GOOGLE_CLIENT_SECRET
    settings.GOOGLE_CLIENT_ID = "client-123"
    settings.GOOGLE_CLIENT_SECRET = "secret-abc"
    state, _verifier, _nonce = encode_oauth_state("google", "/dashboard")
    try:
        response = await client.get(
            f"/api/v1/auth/oauth/google/callback?code=attacker-code&state={state}",
            cookies={"oauth_state": "attacker-controlled-nonce"},
            follow_redirects=False,
        )
        assert response.status_code == 400
    finally:
        settings.GOOGLE_CLIENT_ID = old_google_id
        settings.GOOGLE_CLIENT_SECRET = old_google_secret


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
async def test_oauth_authorize_pages_to_provider_and_binds_session(client: AsyncClient) -> None:
    """The authorize endpoint returns a 200 page (reliable cookie path through
    the Next.js proxy) that carries the session-binding oauth_state cookie,
    PKCE challenge and state token before navigating to the provider."""
    old_google_id = settings.GOOGLE_CLIENT_ID
    old_google_secret = settings.GOOGLE_CLIENT_SECRET
    settings.GOOGLE_CLIENT_ID = "client-123"
    settings.GOOGLE_CLIENT_SECRET = "secret-abc"
    try:
        response = await client.get("/api/v1/auth/oauth/google/authorize", follow_redirects=False)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert response.headers.get("cache-control") == "no-store"
        body = response.text
        assert "https://accounts.google.com/o/oauth2/v2/auth" in body
        assert "client_id=client-123" in body
        assert "state=" in body
        # PKCE must be offered to the provider.
        assert "code_challenge=" in body
        assert "code_challenge_method=S256" in body
        # Force Google to always show the account chooser AND the consent
        # ("continue") page, even for previously-authorized test users.
        assert "prompt=select_account+consent" in body
        set_cookie = "; ".join(response.headers.get_list("set-cookie", []))
        assert "oauth_state=" in set_cookie
        assert "HttpOnly" in set_cookie
    finally:
        settings.GOOGLE_CLIENT_ID = old_google_id
        settings.GOOGLE_CLIENT_SECRET = old_google_secret


async def test_oauth_authorize_navigates_with_raw_query_separators(client: AsyncClient) -> None:
    """The provider URL must reach the browser with real ``&`` separators.

    The authorize page embeds the URL in two different contexts, each needing a
    different encoding: inside the HTML ``content="..."`` attribute ``&`` is
    written ``&amp;``, but inside the JS string that actually performs the
    navigation it must stay raw. Escaping the JS string as HTML sent the literal
    text ``&amp;`` to Google, so the query never split into parameters and the
    provider rejected the request with "Missing required parameter:
    redirect_uri" — a login that could not start.
    """
    old_google_id = settings.GOOGLE_CLIENT_ID
    old_google_secret = settings.GOOGLE_CLIENT_SECRET
    settings.GOOGLE_CLIENT_ID = "client-123"
    settings.GOOGLE_CLIENT_SECRET = "secret-abc"
    try:
        response = await client.get("/api/v1/auth/oauth/google/authorize", follow_redirects=False)
        assert response.status_code == 200
        body = response.text

        # The JS navigation carries raw separators, so redirect_uri is a real
        # parameter and not swallowed into one giant &amp;-joined value.
        js_nav = re.search(r'window\.location\.replace\("([^"]+)"\)', body)
        assert js_nav is not None, "authorize page must navigate via window.location.replace"
        js_url = js_nav.group(1)
        assert "&amp;" not in js_url
        assert "&redirect_uri=" in js_url

        # The HTML attribute keeps the entity form, which is correct there.
        meta = re.search(r'content="0;url=([^"]+)"', body)
        assert meta is not None, "authorize page must carry a meta refresh fallback"
        assert "&amp;" in meta.group(1)
    finally:
        settings.GOOGLE_CLIENT_ID = old_google_id
        settings.GOOGLE_CLIENT_SECRET = old_google_secret
