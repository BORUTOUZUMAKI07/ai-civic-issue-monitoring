from __future__ import annotations

import json
import logging
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.redis import redis_client
from src.core.security import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password_async,
    is_token_blacklisted,
    verify_password_async,
)
from src.errors import (
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidToken,
    TokenRevoked,
    UnauthorizedError,
    UserNotFound,
)
from src.models.user import User, UserRole
from src.repositories.user_repository import UserRepository

logger = logging.getLogger("civicpulse")

# Refresh-token rotation + reuse detection (OAuth 2.0 BCP / RFC 9700): each
# refresh token carries a stable session id (``sid``) and a unique ``jti``.
# Redis keeps one record per session holding the CURRENT jti plus the
# immediately-previous one (short grace window for concurrent 401 retries). If
# a presented jti matches neither, the token was already rotated out — a
# replay — so the whole session family is revoked.
_REFRESH_SESSION_PREFIX = "refresh:session:"
_REFRESH_REVOKED_PREFIX = "refresh:revoked:"
_REFRESH_TTL = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
_REUSE_GRACE_SECONDS = 30

_ROTATE_REFRESH_LUA = """
local rec = redis.call('GET', KEYS[1])
if not rec then
    return -1
end
local presented = ARGV[1]
local new_jti = ARGV[2]
local grace = tonumber(ARGV[3])
local now = tonumber(ARGV[5])
local obj = cjson.decode(rec)
if obj.jti == presented then
    obj.prev_jti = obj.jti
    obj.prev_at = now
    obj.jti = new_jti
    redis.call('SET', KEYS[1], cjson.encode(obj), 'EX', ARGV[4])
    return 1
end
if obj.prev_jti == presented and (now - (obj.prev_at or 0)) <= grace then
    obj.prev_jti = obj.jti
    obj.prev_at = now
    obj.jti = new_jti
    redis.call('SET', KEYS[1], cjson.encode(obj), 'EX', ARGV[4])
    return 1
end
return 0
"""


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def register(self, email: str, password: str, full_name: str, role: str = "field_worker") -> User:
        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise EmailAlreadyExists()

        user_role = UserRole(role) if role in [r.value for r in UserRole] else UserRole.field_worker
        user = User(
            email=email,
            password_hash=await hash_password_async(password),
            full_name=full_name,
            role=user_role,
        )
        return await self.user_repo.create(user)

    async def login(self, email: str, password: str) -> tuple[str, str]:
        user = await self.user_repo.get_by_email(email)
        if not user or not await verify_password_async(password, user.password_hash):
            raise InvalidCredentials()
        if not user.is_active:
            raise UnauthorizedError(detail="Account is deactivated.")

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        await store_refresh_session(refresh_token)

        return access_token, refresh_token

    async def refresh(self, refresh_token: str) -> tuple[str, str]:
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise InvalidToken()

        if payload.get("type") != "refresh":
            raise InvalidToken()

        jti = payload.get("jti")
        sid = payload.get("sid")

        if jti and await is_token_blacklisted(jti):
            raise TokenRevoked()

        user_id = payload.get("sub")
        user = await self.user_repo.get(int(user_id))
        if not user:
            raise UserNotFound()

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})

        if sid and jti:
            revoked = await redis_client.get(f"{_REFRESH_REVOKED_PREFIX}{user.id}")
            if revoked:
                raise TokenRevoked()
            new_refresh = create_refresh_token({"sub": str(user.id)}, sid=sid)
            new_jti = decode_token(new_refresh).get("jti", "")
            result = await redis_client.eval(
                _ROTATE_REFRESH_LUA,
                1,
                f"{_REFRESH_SESSION_PREFIX}{sid}",
                jti,
                new_jti,
                str(_REUSE_GRACE_SECONDS),
                str(_REFRESH_TTL),
                str(int(time.time())),
            )
            result = int(result)
            if result == 0:
                # Replay: the presented token was already rotated out. Revoke the
                # whole session family.
                await self._revoke_refresh_family(user.id)
                raise TokenRevoked()
            if result == -1:
                # No session record for this sid. Reject rather than rotate — a
                # missing record isn't proof of replay, so no family revocation.
                raise TokenRevoked()
        else:
            new_refresh = create_refresh_token({"sub": str(user.id)})
            await store_refresh_session(new_refresh)

        if jti:
            exp = payload.get("exp")
            if exp:
                ttl = int(exp) - int(time.time())
                if ttl > 0:
                    await blacklist_token(jti, ttl)

        return access_token, new_refresh

    async def logout(self, refresh_token: Optional[str], access_token: Optional[str] = None) -> None:
        # Blacklist the presented refresh token and, when available, the access
        # token so neither remains usable after sign-out.
        for token in (access_token, refresh_token):
            if not token:
                continue
            try:
                payload = decode_token(token)
                jti = payload.get("jti")
                exp = payload.get("exp")
                if jti and exp:
                    ttl = int(exp) - int(time.time())
                    if ttl > 0:
                        await blacklist_token(jti, ttl)
                sid = payload.get("sid")
                if sid:
                    await redis_client.delete(f"{_REFRESH_SESSION_PREFIX}{sid}")
            except Exception:
                # Best-effort: a malformed token should not block sign-out and
                # the cookies are cleared regardless.
                logger.warning("logout: failed to blacklist a token")
                continue

    async def _revoke_refresh_family(self, user_id: int) -> None:
        """Kill every refresh token for a user after a replay is detected."""
        try:
            await redis_client.setex(f"{_REFRESH_REVOKED_PREFIX}{user_id}", _REFRESH_TTL, "1")
        except Exception as e:
            logger.warning("refresh: failed to revoke family for user %s: %s", user_id, e)

    async def get_me(self, user_id: int) -> User:
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        return user


async def store_refresh_session(refresh_token: str) -> None:
    """Record a freshly-issued refresh token's sid/jti so rotation and reuse
    detection have a session anchor. Best-effort: if Redis is down we can't
    detect reuse, but the token itself is still valid."""
    try:
        payload = decode_token(refresh_token)
        sid = payload.get("sid")
        jti = payload.get("jti")
        if not sid or not jti:
            return
        record = json.dumps(
            {
                "jti": jti,
                "prev_jti": None,
                "prev_at": 0,
            }
        )
        await redis_client.setex(f"{_REFRESH_SESSION_PREFIX}{sid}", _REFRESH_TTL, record)
    except Exception as e:
        logger.warning("refresh: failed to store session record: %s", e)
