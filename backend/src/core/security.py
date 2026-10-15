from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from src.core.config import settings
from src.shared.errors import InvalidToken, TokenExpired

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    # `passlib` is untyped, so `pwd_context.*` is `Any`; the explicit
    # conversion keeps the declared return type honest instead of laundering
    # `Any` through a `-> str` signature.
    return str(pwd_context.hash(password))


def verify_password(plain: str, hashed: str) -> bool:
    return bool(pwd_context.verify(plain, hashed))


# The legacy fixed sentinel stored for OAuth-created accounts before it was
# replaced with a per-account random value.  Any account whose hash still
# verifies this literal is an OAuth account whose "password" was public
# knowledge, so it must never be accepted again.
_LEGACY_OAUTH_SENTINELS = ("!",)


def verify_password_for_login(plain: str, hashed: str, *, oauth_provider: str | None = None) -> bool:
    """Verify a password for an *interactive* login.

    Two hard refusals sit in front of the Argon2 comparison:

    * Accounts bound to an OAuth provider have no password at all.  Accepting
      one would mean accepting whatever sentinel the hash was built from, so
      the check is refused before any comparison runs.
    * The fixed legacy sentinel ``"!"`` is rejected outright, closing the hole
      for accounts created before the random sentinel was introduced.

    Returns ``False`` (never raises) so callers keep their uniform
    "invalid credentials" response and do not leak which branch tripped.
    """
    if oauth_provider:
        return False
    if plain in _LEGACY_OAUTH_SENTINELS:
        return False
    if not hashed:
        return False
    try:
        return bool(pwd_context.verify(plain, hashed))
    except Exception:
        # A malformed or unknown hash must fail closed, not crash login into a
        # 500 that tells an attacker the account exists.
        return False


async def hash_password_async(password: str) -> str:
    """Argon2 hashing is ~100-200ms of CPU — offload it so the event loop isn't
    blocked for every login/registration."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(verify_password, plain, hashed)


async def verify_password_for_login_async(plain: str, hashed: str, *, oauth_provider: str | None = None) -> bool:
    """Async wrapper for :func:`verify_password_for_login`.

    The OAuth/sentinel refusals run *before* the Argon2 work, so an OAuth-bound
    account costs no CPU on a rejected login — a password-guessing attacker
    cannot use those accounts as a free hashing oracle either.
    """
    if oauth_provider or plain in _LEGACY_OAUTH_SENTINELS or not hashed:
        return verify_password_for_login(plain, hashed, oauth_provider=oauth_provider)
    return await asyncio.to_thread(verify_password, plain, hashed)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    jti: Optional[str] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update(
        {
            "exp": expire,
            "type": "access",
            "jti": jti or uuid4().hex,
        }
    )
    # `python-jose` ships no type information: `jwt.encode` is `Any`, and
    # returning it straight from a `-> str` function is exactly the kind of
    # hole that lets a non-string silently travel down the stack. It always
    # is a str; saying so costs nothing.
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def create_ws_ticket(user_id: int, *, ttl_seconds: int = 60) -> str:
    """Mint a short-lived, single-purpose ticket for the WebSocket handshake.

    WebSocket clients cannot attach the HttpOnly access cookie, so the browser
    has to pass *some* credential in the query string, where it lands in browser
    history and proxy logs. Handing over a full access token would expose an
    API-wide bearer credential for its whole lifetime; this ticket instead lives
    for ``ttl_seconds`` and carries ``type="ws"``, which the WebSocket route
    accepts and every other route rejects.
    """
    to_encode: dict = {"sub": str(user_id)}
    expire = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    to_encode.update({"exp": expire, "type": "ws"})
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def create_refresh_token(
    data: dict,
    sid: Optional[str] = None,
    jti: Optional[str] = None,
) -> str:
    """Mint a refresh token.

    ``sid`` is a stable session identifier shared by every token issued for the
    same login session (it survives rotation), so reuse detection can tie a
    replayed token back to its session. ``jti`` is unique per token and changes
    on every rotation.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update(
        {
            "exp": expire,
            "type": "refresh",
            "jti": jti or uuid4().hex,
            "sid": sid or uuid4().hex,
        }
    )
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def create_2fa_challenge_token(user_id: int) -> str:
    """Mint a short-lived challenge token for the 2FA verification step.

    The token is valid for 5 minutes and carries type="2fa_challenge" so it
    cannot be confused with access or refresh tokens.

    It *does* carry a ``jti``. The previous version deliberately omitted one
    on the grounds that the token was "consumed exactly once" — but nothing
    anywhere ever consumed it, so the same challenge could be replayed for its
    whole 5-minute life. That is exactly the window in which an attacker who
    has lifted the challenge out of a log, a proxy trace or an XSS'd fetch
    wants to sit and try TOTP codes. Single-use is now enforced by the
    ``/2fa/verify`` endpoint via the ``jti``.
    """
    to_encode: dict = {"sub": str(user_id)}
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    to_encode.update({"exp": expire, "type": "2fa_challenge", "jti": uuid4().hex})
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        # Copy into a real dict: `jwt.decode` is untyped, so this is where the
        # guarantee that callers get an actual mapping has to be made.
        return dict(payload)
    except ExpiredSignatureError:
        raise TokenExpired()
    except JWTError:
        raise InvalidToken()


async def blacklist_token(jti: str, ttl_seconds: int) -> None:
    from src.core.redis import redis_client

    await redis_client.setex(f"jwt:blacklist:{jti}", ttl_seconds, "1")


async def is_token_blacklisted(jti: str) -> bool:
    from src.core.redis import redis_client

    try:
        result = await redis_client.get(f"jwt:blacklist:{jti}")
        return result is not None
    except Exception:
        return False
