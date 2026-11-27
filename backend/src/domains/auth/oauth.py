from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import src.core.redis as redis_module
from src.core.config import settings
from src.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password_async,
)
from src.domains.users.models.user import User, UserRole
from src.domains.users.repositories.user_repository import UserRepository
from src.shared.errors import InvalidToken, OAuthError, OAuthNotConfigured, OAuthStateInvalid

logger = logging.getLogger("civicpulse")

_OAUTH_STATE_PREFIX = "oauth:state:"
_OAUTH_STATE_TTL = 600
_OAUTH_HANDOFF_PREFIX = "oauth:handoff:"

# Codes are generated with token_urlsafe, so anything outside this alphabet is
# an attempted key-injection / probe and can be rejected before touching Redis.
_TOKEN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


async def _atomic_getdel(key: str):
    """GETDEL is one Redis command; a get()+delete() pair races under awaits."""
    return await redis_module.redis_client.getdel(key)


class OAuthProfile(dict):
    """Provider identity payload with attribute access for new code."""

    def __init__(self, sub: str, email: str | None = None, name: str | None = None, email_verified: bool = False):
        email_norm = (email or "").lower() if email else ""
        super().__init__(
            provider_id=str(sub or ""),
            sub=str(sub or ""),
            email=email_norm,
            name=name or "",
            verified=bool(email_verified),
            email_verified=bool(email_verified),
        )
        self.sub = str(sub or "")
        self.email = email_norm or None
        self.name = name or ""
        self.email_verified = bool(email_verified)

    @property
    def provider(self) -> str | None:
        return self.get("provider")  # type: ignore[return-value]


class OAuthProvider:
    """OAuth provider client (generic, configurable)."""

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
        # GitHub emails endpoint (kept for compatibility/tests that inspect instances)
        self.emails_url = "https://api.github.com/user/emails"

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authorize_uri(
        self,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
        code_challenge_method: str = "S256",
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.scope,
            "state": state,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method
        if self.client_kwargs:
            for kv in self.client_kwargs.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[k] = v
        return f"{self.authorize_url}?{urlencode(params)}"

    async def fetch_user(self, code: str, redirect_uri: str, code_verifier: str | None = None) -> dict[str, Any]:
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        token_headers = {"Accept": "application/json"} if self.name == "github" else None
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(self.token_url, data=data, headers=token_headers)
            if resp.status_code >= 400:
                raise OAuthError(f"{self.name} token exchange failed (HTTP {resp.status_code})")
            token_json = resp.json()
            access_token = token_json.get("access_token")
            if not access_token:
                raise OAuthError(f"{self.name} token exchange failed: {token_json}")
            user_resp = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            if user_resp.status_code >= 400:
                raise OAuthError(f"{self.name} userinfo failed (HTTP {user_resp.status_code})")
            user_json = user_resp.json()
            if self.name == "github":
                emails_resp = await client.get(
                    self.emails_url,
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                if emails_resp.status_code >= 400:
                    raise OAuthError(f"GitHub emails failed (HTTP {emails_resp.status_code})")
                records = emails_resp.json() or []
                primary_verified = next(
                    (r.get("email") for r in records if r.get("primary") and r.get("verified")), None
                )
                verified_email = primary_verified or next((r.get("email") for r in records if r.get("verified")), None)
                email = (verified_email or "").lower()
                profile: dict[str, Any] = {
                    "provider": "github",
                    "provider_id": str(user_json.get("id")),
                    "email": email,
                    "name": user_json.get("name") or user_json.get("login") or "",
                    "verified": bool(verified_email),
                }
                profile["sub"] = profile["provider_id"]
                profile["email_verified"] = profile["verified"]
                return profile

            # Google / OIDC
            email_verified = bool(user_json.get("email_verified", False))
            email = (user_json.get("email") or "").lower()
            if email and not email_verified:
                # Do not trust an unverified email for identity/linking.
                email = ""
            profile = {
                "provider": "google",
                "provider_id": str(user_json.get("sub")),
                "email": email,
                "name": user_json.get("name") or (email or user_json.get("email", "")),
                "verified": bool(email_verified and email),
            }
            profile["sub"] = profile["provider_id"]
            profile["email_verified"] = profile["verified"]
            return profile


def _unusable_password() -> str:
    return secrets.token_urlsafe(32)


async def get_user_by_oauth_identity(db, provider: str, sub: str) -> User | None:
    if not sub:
        return None
    stmt = select(User).where(User.oauth_provider == provider, User.oauth_sub == sub)
    result = await db.execute(stmt)
    user: User | None = result.scalar_one_or_none()
    return user


def _profile_field(profile: Any, key: str, default: Any = None) -> Any:
    if isinstance(profile, dict):
        return profile.get(key, default)
    return getattr(profile, key, default)


async def login_with_provider(db, provider: OAuthProvider, profile: dict | Any) -> tuple[User, str, str]:
    """Authenticate or provision a user from an OAuth identity.

    Compatible with both dict profiles (legacy/tests) and OAuthProfile-like objects.
    """
    repo = UserRepository(db)
    email = (_profile_field(profile, "email") or "") or None
    if isinstance(email, str):
        email = email.lower() or None
    verified = bool(_profile_field(profile, "verified", _profile_field(profile, "email_verified", False)))
    provider_name = _profile_field(profile, "provider") or provider.name
    provider_sub = str(_profile_field(profile, "provider_id") or _profile_field(profile, "sub") or "")
    name = _profile_field(profile, "name") or ""

    if not provider_sub:
        raise OAuthError("OAuth provider did not return a stable user id.")

    user = await get_user_by_oauth_identity(db, provider_name, provider_sub)
    created_here = False

    if user is None:
        candidate = await repo.get_by_email(email) if email else None
        if candidate is not None:
            if candidate.oauth_provider and candidate.oauth_provider != provider_name:
                logger.warning(
                    "oauth: refusing to link %s identity to %s already bound to %s",
                    provider_name,
                    email,
                    candidate.oauth_provider,
                )
                raise OAuthError("This email is already registered with a different sign-in method.")
            # Same provider, different subject: the provider's subject is the
            # authoritative identity. Only relink when the provider also
            # asserted a verified email, otherwise an attacker controlling an
            # unverified email claim could take over the existing account.
            if (
                candidate.oauth_provider == provider_name
                and candidate.oauth_sub
                and candidate.oauth_sub != provider_sub
                and not verified
            ):
                raise OAuthError("This email is already linked to a different provider identity.")
            has_local_password = bool(candidate.password_hash) and candidate.oauth_provider is None
            if has_local_password and not verified:
                logger.warning(
                    "oauth: refusing to link unverified %s email %s into password-protected account",
                    provider_name,
                    email,
                )
                raise OAuthError(
                    "This email already belongs to a password-protected account. Sign in with that password instead."
                )
            user = candidate

        if user is None:
            user = User(
                email=email or f"{provider_name}_{provider_sub}@oauth.invalid",
                password_hash=await hash_password_async(_unusable_password()),
                full_name=name or (email.split("@", 1)[0] if email else f"{provider_name.title()} User"),
                role=UserRole.field_worker,
                oauth_provider=provider_name,
                oauth_sub=provider_sub or None,
                email_verified=bool(verified and email),
                email_verified_at=datetime.now(timezone.utc) if (verified and email) else None,
            )
            try:
                user = await repo.create(user)
                created_here = True
            except IntegrityError:
                # Two simultaneous first logins can race past the lookup. The
                # unique (provider, sub) index decides the winner; reload it
                # instead of turning a normal concurrency case into a 500.
                await db.rollback()
                user = await get_user_by_oauth_identity(db, provider_name, provider_sub)
                if user is None:
                    raise OAuthError("Could not provision the OAuth account.")
        else:
            changed = False
            user.oauth_provider = provider_name
            if provider_sub and user.oauth_sub != provider_sub:
                user.oauth_sub = provider_sub
                changed = True
            if name and name != user.full_name:
                user.full_name = name
                changed = True
            if verified and email and not getattr(user, "email_verified", True):
                user.email_verified = True
                user.email_verified_at = datetime.now(timezone.utc)
                changed = True
            # Ensure binding fields persist even if no other visible field changed.
            await db.commit()
            await db.refresh(user)
            _ = changed
    else:
        changed = False
        if name and name != user.full_name:
            user.full_name = name
            changed = True
        if verified and email and not getattr(user, "email_verified", True):
            user.email_verified = True
            user.email_verified_at = datetime.now(timezone.utc)
            changed = True
        if changed:
            await db.commit()
            await db.refresh(user)

    if not user.is_active:
        from src.shared.errors import UnauthorizedError

        raise UnauthorizedError(detail="Account is deactivated.")

    from src.domains.auth.services.auth_service import (
        clear_user_revocation,
        store_refresh_session,
    )

    await clear_user_revocation(user.id)
    refresh_token = create_refresh_token({"sub": str(user.id)})
    await store_refresh_session(refresh_token)
    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    logger.debug("oauth: signed in %s (created=%s)", user.email, created_here)
    return user, access_token, refresh_token


def get_provider(name: str) -> OAuthProvider:
    if name == "google":
        return OAuthProvider(
            name="google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",  # nosec B106 - URL, not a credential
            userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scope="openid email profile",
            client_kwargs="access_type=online&prompt=select_account consent",
        )
    if name == "github":
        return OAuthProvider(
            name="github",
            authorize_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",  # nosec B106 - URL, not a credential
            userinfo_url="https://api.github.com/user",
            client_id=settings.GITHUB_CLIENT_ID,
            client_secret=settings.GITHUB_CLIENT_SECRET,
            scope="read:user user:email",
            client_kwargs="",
        )
    raise OAuthNotConfigured(name)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url(digest)


def _now_plus(minutes: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


# --- Legacy JWT-based state helpers (compat; tests may still use them) ---
def encode_oauth_state(provider: str, redirect: str) -> tuple[str, str, str]:
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    state = str(
        jwt.encode(
            {
                "provider": provider,
                "redirect": redirect or "/dashboard",
                "nonce": nonce,
                "cv": verifier,
                "exp": _now_plus(settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
    )
    return state, verifier, nonce


def _decode_oauth_payload(provider: str, state: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except Exception:
        raise OAuthStateInvalid()
    if payload.get("provider") != provider:
        raise OAuthStateInvalid()
    if not payload.get("nonce"):
        raise OAuthStateInvalid()
    redirect = payload.get("redirect") or "/dashboard"
    if isinstance(redirect, str) and redirect.startswith("/") and "://" not in redirect:
        return {
            "provider": provider,
            "redirect": redirect,
            "nonce": payload["nonce"],
            "code_verifier": payload.get("cv") or "",
        }
    raise OAuthStateInvalid()


def decode_oauth_state(provider: str, state: str) -> str:
    return str(_decode_oauth_payload(provider, state)["redirect"])


def decode_oauth_bundle(provider: str, state: str) -> dict[str, Any]:
    return _decode_oauth_payload(provider, state)


# --- Hardened server-side one-time state/PKCE storage (production flow) ---
async def store_oauth_state(provider: str, redirect: str) -> tuple[str, str, str]:
    """Create and persist a one-time OAuth state/PKCE bundle in Redis.

    Returns (state_id, code_verifier, nonce). The state_id is placed in the
    authorize URL; the nonce is stored in an HttpOnly cookie for binding.
    """
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    state_id = secrets.token_urlsafe(24)
    safe_redirect = (
        redirect
        if isinstance(redirect, str)
        and redirect.startswith("/")
        and "://" not in redirect
        and not redirect.startswith("//")
        else "/dashboard"
    )
    bundle = {
        "provider": provider,
        "redirect": safe_redirect,
        "verifier": verifier,
        "nonce": nonce,
    }
    try:
        await redis_module.redis_client.setex(f"{_OAUTH_STATE_PREFIX}{state_id}", _OAUTH_STATE_TTL, json.dumps(bundle))
    except Exception as exc:
        logger.error("oauth: failed to persist state: %s", exc)
        raise OAuthError("Could not start OAuth sign-in. Please try again.")
    return state_id, verifier, nonce


async def consume_oauth_state(provider: str, state_id: str) -> dict[str, Any]:
    """Atomically consume a one-time OAuth state bundle. Raises on replay/invalid."""
    if not _TOKEN_ID_RE.fullmatch(state_id or ""):
        raise OAuthStateInvalid()
    key = f"{_OAUTH_STATE_PREFIX}{state_id}"
    try:
        raw = await _atomic_getdel(key)
    except Exception as exc:
        logger.warning("oauth: failed to consume state: %s", exc)
        raise OAuthStateInvalid()
    if not raw:
        raise OAuthStateInvalid()
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        raise OAuthStateInvalid()
    if not isinstance(payload, dict) or payload.get("provider") != provider:
        raise OAuthStateInvalid()
    redirect = payload.get("redirect") or "/dashboard"
    if not isinstance(redirect, str) or not redirect.startswith("/") or "://" in redirect or redirect.startswith("//"):
        redirect = "/dashboard"
    return {
        "redirect": redirect,
        "code_verifier": payload.get("verifier") or "",
        "nonce": payload.get("nonce") or "",
    }


# --- One-time callback -> frontend handoff ---------------------------------
def _safe_redirect(value: str | None) -> str:
    """Only same-origin absolute paths may be returned to the browser."""
    if (
        isinstance(value, str)
        and value.startswith("/")
        and not value.startswith("//")
        and "://" not in value
        and "\\" not in value
    ):
        return value
    return "/dashboard"


async def create_oauth_handoff(refresh_token: str, redirect: str) -> str:
    """Store the OAuth result under a random code; return only that code.

    The callback URL carries `?code=<random>` instead of tokens or state. Access
    logs, browser history and Referer headers therefore never see a credential.
    """
    code = secrets.token_urlsafe(32)
    payload = {"refresh_token": refresh_token, "redirect": _safe_redirect(redirect)}
    ttl = max(1, int(settings.OAUTH_HANDOFF_TTL_SECONDS))
    try:
        await redis_module.redis_client.setex(f"{_OAUTH_HANDOFF_PREFIX}{code}", ttl, json.dumps(payload))
    except Exception as exc:
        logger.error("oauth: failed to store handoff: %s", exc)
        raise OAuthError("Could not finish OAuth sign-in. Please try again.")
    return code


async def consume_oauth_handoff(code: str) -> dict[str, str]:
    """Consume a handoff exactly once. Replay raises InvalidToken."""
    if not _TOKEN_ID_RE.fullmatch(code or ""):
        raise InvalidToken()
    try:
        raw = await _atomic_getdel(f"{_OAUTH_HANDOFF_PREFIX}{code}")
    except Exception as exc:
        logger.warning("oauth: failed to consume handoff: %s", exc)
        raise InvalidToken()
    if not raw:
        raise InvalidToken()
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        raise InvalidToken()
    if not isinstance(payload, dict):
        raise InvalidToken()
    refresh_token = payload.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise InvalidToken()
    return {"refresh_token": refresh_token, "redirect": _safe_redirect(payload.get("redirect"))}
