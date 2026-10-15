"""OAuth2 (authorization-code) sign-in for Google and GitHub.

Implements the flow manually over ``httpx`` rather than pulling in an OAuth
framework adapter, which keeps the state handling explicit and lets us embed
the intended post-login redirect inside a signed ``state`` token (CSRF-safe).

All credentials come from settings; when a provider's client id/secret are
empty the provider is considered "not configured" and its endpoints refuse to
run (the UI simply hides the button).

Flow:
    authorize -> 200 page sets a session-binding cookie (state signed, carries
                 provider, redirect, PKCE verifier) and bounces to provider
    provider  -> 302 to callback?code=...&state=...
    callback  -> verify cookie-bound state, exchange code (PKCE verifier),
                 fetch profile (with provider email-verification flag),
                 upsert user, set JWT cookies
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from urllib.parse import urlencode

import httpx
from jose import jwt
from sqlalchemy import select

from src.core.config import settings
from src.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password_async,
)
from src.domains.users.models.user import User, UserRole
from src.domains.users.repositories.user_repository import UserRepository
from src.shared.errors import OAuthError, OAuthNotConfigured, OAuthStateInvalid

logger = logging.getLogger("civicpulse")


def _unusable_password() -> str:
    """A random, never-published string whose Argon2 hash is stored in place of
    a password for OAuth-created accounts.

    It must be *random per account* rather than a fixed sentinel such as ``"!"``:
    a fixed value is a known plaintext, and ``verify_password("!", hash("!"))``
    returns ``True``, which turns every OAuth account into one whose password is
    public knowledge.  A fresh 256-bit value is never transmitted, never stored
    in plaintext, and can never be guessed.

    This is defence in depth only — password login for OAuth-bound accounts is
    refused outright by ``verify_password_for_login`` regardless of the hash.
    """
    return secrets.token_urlsafe(32)


async def get_user_by_oauth_identity(db, provider: str, sub: str) -> User | None:
    """Look an account up by the provider's subject id, never by email."""
    if not sub:
        return None
    stmt = select(User).where(User.oauth_provider == provider, User.oauth_sub == sub)
    result = await db.execute(stmt)
    user: User | None = result.scalar_one_or_none()
    return user


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
            # PKCE (RFC 7636): bind the authorization code to THIS authorize
            # request so an intercepted or substituted code cannot be redeemed
            # without the matching verifier. Both providers support S256.
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method
        if self.client_kwargs:
            # e.g. access_type=offline&prompt=consent for Google
            for kv in self.client_kwargs.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[k] = v
        return f"{self.authorize_url}?{urlencode(params)}"

    async def fetch_user(self, code: str, redirect_uri: str, code_verifier: str | None = None) -> dict:
        """Exchange the authorization code and return the normalized profile.

        ``code_verifier`` is the PKCE secret minted on the authorize request;
        when present it is sent on the token exchange so the provider can
        prove the code came from that authorize (RFC 7636). The profile also
        carries ``verified`` — the provider's email-verification flag — which
        ``login_with_provider`` requires before linking a provider identity
        into an account that has a local password.

        Google: the OIDC userinfo endpoint returns ``email_verified`` whenever
        the ``email`` scope is granted (it is: ``openid email profile``).
        GitHub: ``/user``'s ``email`` is the *public profile* address and
        GitHub does not require it to be verified or primary, so it is never
        trusted; ``/user/emails`` is always consulted and a verified address
        (primary preferred) is required, mirroring our url-shortner and Nexus
        AI projects.
        """
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
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                if emails_resp.status_code >= 400:
                    raise OAuthError(f"GitHub emails failed (HTTP {emails_resp.status_code})")
                records = emails_resp.json() or []
                primary_verified = next(
                    (r.get("email") for r in records if r.get("primary") and r.get("verified")), None
                )
                verified_email = primary_verified or next((r.get("email") for r in records if r.get("verified")), None)
                return {
                    "provider": "github",
                    "provider_id": str(user_json.get("id")),
                    "email": (verified_email or "").lower(),
                    "name": user_json.get("name") or user_json.get("login") or "",
                    "verified": bool(verified_email),
                }
            # google — OIDC userinfo emits `email_verified` with the email scope.
            return {
                "provider": "google",
                "provider_id": str(user_json.get("sub")),
                "email": (user_json.get("email") or "").lower(),
                "name": user_json.get("name") or user_json.get("email", ""),
                "verified": bool(user_json.get("email_verified", False)),
            }


def get_provider(name: str) -> OAuthProvider:
    if name == "google":
        return OAuthProvider(
            name="google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",  # an endpoint, not a secret  # nosec B106
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
            token_url="https://github.com/login/oauth/access_token",  # an endpoint, not a secret  # nosec B106
            userinfo_url="https://api.github.com/user",
            client_id=settings.GITHUB_CLIENT_ID,
            client_secret=settings.GITHUB_CLIENT_SECRET,
            scope="read:user user:email",
            client_kwargs="prompt=select_account",
        )
    raise OAuthNotConfigured(name)


def encode_oauth_state(provider: str, redirect: str) -> tuple[str, str, str]:
    """Create a fresh OAuth authorization session.

    Returns ``(state_token, code_verifier, nonce)``:

    * ``state_token`` — signed JWT carrying the provider, the post-login
      redirect, a fresh random ``nonce`` and the PKCE code verifier. The
      provider echoes it back verbatim on the callback, so it is the only
      thing a cross-site caller can influence — and it can be neither forged
      (signed) nor predicted (fresh high-entropy nonce per initiation).
    * ``code_verifier`` — a high-entropy PKCE (RFC 7636) secret. Only its
      S256 challenge (see :func:`code_challenge`) is shown to the provider;
      the verifier itself is sent on the token exchange, so an intercepted or
      substituted authorization code cannot be redeemed by whoever stole it.
    * ``nonce`` — the browser-session binding. The authorize route stores it
      in an ``oauth_state`` cookie and the callback only accepts a state whose
      nonce matches that cookie. Without it, an attacker who began a flow for
      their *own* account could hand the victim a valid state + code and log
      the victim into the attacker's account (login-CSRF / session fixation).
    """
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


def code_challenge(verifier: str) -> str:
    """RFC 7636 S256 PKCE challenge for ``verifier`` (unpadded base64url)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _decode_oauth_payload(provider: str, state: str) -> dict:
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except Exception:
        raise OAuthStateInvalid()
    if payload.get("provider") != provider:
        raise OAuthStateInvalid()
    # Fail closed: state tokens without a nonce (pre-fix or hand-built) are
    # refused so the browser-session binding can never be silently downgraded.
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
    """Validate the state token and return the embedded redirect path.

    Raises ``OAuthStateInvalid`` on any mismatch.
    """
    return str(_decode_oauth_payload(provider, state)["redirect"])


def decode_oauth_bundle(provider: str, state: str) -> dict:
    """Validate the state token and return the full session (``redirect``,
    ``nonce``, ``code_verifier``) the callback route needs."""
    return _decode_oauth_payload(provider, state)


def _now_plus(minutes: int):
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


async def login_with_provider(db, provider: OAuthProvider, profile: dict) -> tuple[User, str, str]:
    """Upsert a user by provider identity / email and mint JWTs.

    Identity rules (mirrors the pattern used by our url-shortner and Nexus AI
    projects):

    1. Look up by ``(provider, provider_id)`` — the only authoritative link.
    2. Only if no identity link exists, fall back to email to *find a
       pre-existing account to link*.
    3. Never link into an account that is already bound to a *different*
       provider: that is either provider-side account takeover or user
       confusion, and re-binding would hand the account to whoever holds the
       second identity.
    4. Never link into an account that already has a local password unless the
       provider's email is marked verified by the provider.
    """
    repo = UserRepository(db)
    email = profile.get("email")
    if not email:
        raise OAuthError("Your {provider} account has no email address.".format(provider=provider.name))

    provider_name = profile.get("provider") or provider.name
    provider_sub = str(profile.get("provider_id") or "")

    user = await get_user_by_oauth_identity(db, provider_name, provider_sub)
    created_here = False

    if user is None:
        candidate = await repo.get_by_email(email)
        if candidate is not None:
            # A pre-existing account is only linked when it is either already
            # OAuth-bound to this very provider, or has no provider binding and
            # no password (an orphan), or is bound to nothing at all.
            if candidate.oauth_provider and candidate.oauth_provider != provider_name:
                logger.warning(
                    "oauth: refusing to link %s identity to %s already bound to %s",
                    provider_name,
                    email,
                    candidate.oauth_provider,
                )
                raise OAuthError("This email is already registered with a different sign-in method.")
            # Rule 4: never link into an account that carries a *local* password
            # unless the provider has verified the email address. OAuth-created
            # accounts store an unusable random hash, so an existing binding to
            # this very provider (oauth_provider set) is exempt — those users are
            # re-authenticating with the same identity, not taking over an
            # account protected by a password only the real owner knows.
            has_local_password = bool(candidate.password_hash) and candidate.oauth_provider is None
            if has_local_password and not profile.get("verified"):
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
                email=email,
                password_hash=await hash_password_async(_unusable_password()),
                full_name=profile.get("name") or email.split("@", 1)[0],
                role=UserRole.field_worker,
                oauth_provider=provider_name,
                oauth_sub=provider_sub or None,
            )
            user = await repo.create(user)
            created_here = True
        else:
            # Link the provider identity onto the account we found by email.
            user.oauth_provider = provider_name
            if provider_sub:
                user.oauth_sub = provider_sub
            if profile.get("name") and profile["name"] != user.full_name:
                user.full_name = profile["name"]
            await db.commit()
            await db.refresh(user)
    else:
        changed = False
        if profile.get("name") and profile["name"] != user.full_name:
            user.full_name = profile["name"]
            changed = True
        if changed:
            await db.commit()
            await db.refresh(user)

    if not user.is_active:
        from src.shared.errors import UnauthorizedError

        raise UnauthorizedError(detail="Account is deactivated.")

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    from src.domains.auth.services.auth_service import clear_refresh_family_revocation, store_refresh_session

    # Record the refresh session so rotation + reuse detection apply to OAuth
    # sign-ins as well as password logins. A completed OAuth sign-in is a fresh
    # interactive authentication, so it also lifts any post-replay refresh
    # lockout — otherwise the user could sign in but never refresh again.
    await clear_refresh_family_revocation(user.id)
    await store_refresh_session(refresh_token)
    logger.debug("oauth: signed in %s (created=%s)", user.email, created_here)
    return user, access_token, refresh_token
