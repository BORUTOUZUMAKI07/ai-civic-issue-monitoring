from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from passlib.context import CryptContext

from src.core.config import settings
from src.shared.errors import InvalidToken, TokenExpired

JWTError = InvalidTokenError

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return str(pwd_context.hash(password))


def verify_password(plain: str, hashed: str) -> bool:
    return bool(pwd_context.verify(plain, hashed))


_LEGACY_OAUTH_SENTINELS = ("!",)


def verify_password_for_login(plain: str, hashed: str, *, oauth_provider: str | None = None) -> bool:
    if oauth_provider:
        return False
    if plain in _LEGACY_OAUTH_SENTINELS:
        return False
    if not hashed:
        return False
    try:
        return bool(pwd_context.verify(plain, hashed))
    except Exception:
        return False


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(verify_password, plain, hashed)


async def verify_password_for_login_async(plain: str, hashed: str, *, oauth_provider: str | None = None) -> bool:
    if oauth_provider or plain in _LEGACY_OAUTH_SENTINELS or not hashed:
        return verify_password_for_login(plain, hashed, oauth_provider=oauth_provider)
    return await asyncio.to_thread(verify_password, plain, hashed)


def _standard_claims() -> dict:
    return {
        "iat": datetime.now(timezone.utc),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    jti: Optional[str] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update(
        {
            **_standard_claims(),
            "exp": expire,
            "type": "access",
            "jti": jti or uuid4().hex,
        }
    )
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def create_ws_ticket(user_id: int, *, ttl_seconds: int = 60) -> str:
    to_encode: dict = {"sub": str(user_id)}
    expire = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    to_encode.update({**_standard_claims(), "exp": expire, "type": "ws"})
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def create_refresh_token(
    data: dict,
    sid: Optional[str] = None,
    jti: Optional[str] = None,
    fam: Optional[str] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update(
        {
            **_standard_claims(),
            "exp": expire,
            "type": "refresh",
            "jti": jti or uuid4().hex,
            "sid": sid or uuid4().hex,
            "fam": fam or uuid4().hex,
        }
    )
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def create_2fa_challenge_token(user_id: int) -> str:
    to_encode: dict = {"sub": str(user_id)}
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    to_encode.update({**_standard_claims(), "exp": expire, "type": "2fa_challenge", "jti": uuid4().hex})
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
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
