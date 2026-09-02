"""OAuth2 (authorization-code) sign-in for Google and GitHub.

Implements the flow manually over ``httpx`` rather than pulling in an OAuth
framework adapter, which keeps the state handling explicit and lets us embed
the intended post-login redirect inside a signed ``state`` token (CSRF-safe).

All credentials come from settings; when a provider's client id/secret are
empty the provider is considered "not configured" and its endpoints refuse to
run (the UI simply hides the button).

Flow:
    authorize -> 302 to provider consent (state signed, carries redirect)
    provider  -> 302 to callback?code=...&state=...
    callback  -> exchange code, fetch profile, upsert user, set JWT cookies
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx
from jose import jwt

from src.core.config import settings
from src.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
)
from src.errors import OAuthError, OAuthNotConfigured, OAuthStateInvalid
from src.models.user import User, UserRole
from src.repositories.user_repository import UserRepository

logger = logging.getLogger("civicpulse")

# A "password" is required by the schema but OAuth users have none; store an
# unusable hash so direct password login can never succeed for them.
_OAUTH_PASSWORD = "!"  # passlib will never verify this


class OAuthProvider:
    def __init__(
        self,
        *,
        name: str,
        authorize_url: str,
        token_url: str,
        userinfo_url: str,
        client_id: str,
        client_secret: str,
        scope: str,
        client_kwargs: str = "",
    ):
        self.name = name
        self.authorize_url = authorize_url
        self.token_url = token_url
        self.userinfo_url = userinfo_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.client_kwargs = client_kwargs

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authorize_uri(self, redirect_uri: str, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.scope,
            "state": state,
        }
        if self.client_kwargs:
            # e.g. access_type=offline&prompt=consent for Google
            for kv in self.client_kwargs.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[k] = v
        return f"{self.authorize_url}?{urlencode(params)}"

    async def fetch_user(self, code: str, redirect_uri: str) -> dict:
        """Exchange the authorization code and return the normalized profile."""
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            if self.name == "github":
                resp = await client.post(self.token_url, data=data, headers={"Accept": "application/json"})
                token_json = resp.json()
                access_token = token_json.get("access_token")
                if not access_token:
                    raise OAuthError(f"GitHub token exchange failed: {token_json}")
                user_resp = await client.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                user_json = user_resp.json()
                email = user_json.get("email")
                # GitHub only returns the primary verified email here; the /user
                # endpoint may still omit it, in which case we fetch emails.
                if not email:
                    emails_resp = await client.get(
                        "https://api.github.com/user/emails",
                        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                    )
                    for record in emails_resp.json() or []:
                        if record.get("primary") and record.get("verified"):
                            email = record.get("email")
                            break
                return {
                    "provider": "github",
                    "provider_id": str(user_json.get("id")),
                    "email": (email or "").lower(),
                    "name": user_json.get("name") or user_json.get("login") or "",
                }
            else:  # google
                resp = await client.post(self.token_url, data=data)
                token_json = resp.json()
                access_token = token_json.get("access_token")
                if not access_token:
                    raise OAuthError(f"Google token exchange failed: {token_json}")
                user_resp = await client.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                user_json = user_resp.json()
                return {
                    "provider": "google",
                    "provider_id": str(user_json.get("sub")),
                    "email": (user_json.get("email") or "").lower(),
                    "name": user_json.get("name") or user_json.get("email", ""),
                }


def get_provider(name: str) -> OAuthProvider:
    if name == "google":
        return OAuthProvider(
            name="google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scope="openid email profile",
            client_kwargs="access_type=online",
        )
    if name == "github":
        return OAuthProvider(
            name="github",
            authorize_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            userinfo_url="https://api.github.com/user",
            client_id=settings.GITHUB_CLIENT_ID,
            client_secret=settings.GITHUB_CLIENT_SECRET,
            scope="read:user user:email",
        )
    raise OAuthNotConfigured(name)


def encode_oauth_state(provider: str, redirect: str) -> str:
    """Sign a short-lived state token carrying the provider and post-login redirect."""
    return jwt.encode(
        {
            "provider": provider,
            "redirect": redirect or "/dashboard",
            "exp": _now_plus(settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_oauth_state(provider: str, state: str) -> str:
    """Validate the state token and return the embedded redirect path.

    Raises ``OAuthStateInvalid`` on any mismatch.
    """
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except Exception:
        raise OAuthStateInvalid()
    if payload.get("provider") != provider:
        raise OAuthStateInvalid()
    redirect = payload.get("redirect") or "/dashboard"
    if isinstance(redirect, str) and redirect.startswith("/") and "://" not in redirect:
        return redirect
    raise OAuthStateInvalid()


def _now_plus(minutes: int):
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


async def login_with_provider(db, provider: OAuthProvider, profile: dict) -> tuple[User, str, str]:
    """Upsert a user by provider identity / email and mint JWTs."""
    repo = UserRepository(db)
    email = profile.get("email")
    if not email:
        raise OAuthError("Your {provider} account has no email address.".format(provider=provider.name))

    user = await repo.get_by_email(email)
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(_OAUTH_PASSWORD),
            full_name=profile.get("name") or email.split("@", 1)[0],
            role=UserRole.field_worker,
        )
        user = await repo.create(user)
    elif user.full_name != (profile.get("name") or user.full_name):
        user.full_name = profile.get("name") or user.full_name
        await db.commit()
        await db.refresh(user)

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return user, access_token, refresh_token
