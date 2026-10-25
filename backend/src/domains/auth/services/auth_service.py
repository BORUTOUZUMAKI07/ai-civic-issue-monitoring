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
    verify_password_for_login_async,
)
from src.domains.auth.password_reset import revoke_all_refresh_sessions
from src.domains.users.models.user import User, UserRole
from src.domains.users.repositories.user_repository import UserRepository
from src.shared.errors import (
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidToken,
    TokenRevoked,
    UnauthorizedError,
    UserNotFound,
)

logger = logging.getLogger("civicpulse")

_REFRESH_SESSION_PREFIX = "refresh:session:"
_REFRESH_REVOKED_PREFIX = "refresh:revoked:"
_REFRESH_FAMILY_REVOKED_PREFIX = "refresh:revoked:family:"
_REFRESH_FAMILY_INDEX_PREFIX = "refresh:family:"
_REFRESH_USER_SESSIONS_PREFIX = "refresh:user:sessions:"
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
        if not user or not await verify_password_for_login_async(
            password, user.password_hash, oauth_provider=user.oauth_provider
        ):
            raise InvalidCredentials()
        if not user.is_active:
            raise UnauthorizedError(detail="Account is deactivated.")

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        await clear_refresh_family_revocation(user.id)
        await clear_refresh_revocation(user.id)
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
        fam = payload.get("fam")

        if jti and await is_token_blacklisted(jti):
            raise TokenRevoked()

        user_id = payload.get("sub")
        if not user_id:
            raise InvalidToken()
        user = await self.user_repo.get(int(str(user_id)))
        if not user:
            raise UserNotFound()

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})

        if sid and jti:
            if await self._refresh_family_revoked(user.id, fam):
                raise TokenRevoked()
            new_refresh = create_refresh_token({"sub": str(user.id)}, sid=sid, fam=fam)
            new_jti = decode_token(new_refresh).get("jti", "")
            result = await self._rotate_refresh_session(sid, jti, new_jti)
            if result == 0:
                await self._revoke_refresh_family(user.id, fam, sid)
                raise TokenRevoked()
            if result == -1:
                raise TokenRevoked()
        else:
            new_refresh = create_refresh_token({"sub": str(user.id)})
            await store_refresh_session(new_refresh)

        if jti:
            exp = payload.get("exp")
            if exp:
                ttl = int(exp) - int(time.time())
                if ttl > 0:
                    await self._blacklist_best_effort(jti, ttl)

        return access_token, new_refresh

    async def _refresh_family_revoked(self, user_id: int, fam: str | None) -> bool:
        try:
            if await redis_client.get(f"{_REFRESH_REVOKED_PREFIX}{user_id}"):
                return True
            if fam and await redis_client.get(f"{_REFRESH_FAMILY_REVOKED_PREFIX}{fam}"):
                return True
            return False
        except Exception as e:
            logger.warning("refresh: Redis unavailable, treating family as not revoked: %s", e)
            return False

    async def _rotate_refresh_session(self, sid: str, jti: str, new_jti: str) -> int:
        try:
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
        except Exception as e:
            logger.warning("refresh: Redis unavailable, skipping rotation bookkeeping: %s", e)
            return 1
        return int(result)

    async def _blacklist_best_effort(self, jti: str, ttl_seconds: int) -> None:
        try:
            await blacklist_token(jti, ttl_seconds)
        except Exception as e:
            logger.warning("refresh: Redis unavailable, could not blacklist rotated token: %s", e)

    async def logout(self, refresh_token: Optional[str], access_token: Optional[str] = None) -> None:
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
                    fam = payload.get("fam") or await _family_for_sid(sid)
                    if fam:
                        await redis_client.setex(f"{_REFRESH_FAMILY_REVOKED_PREFIX}{fam}", _REFRESH_TTL, "1")
                        await redis_client.delete(f"{_REFRESH_FAMILY_INDEX_PREFIX}{sid}")
            except Exception:
                logger.warning("logout: failed to blacklist a token")
                continue

    async def _revoke_refresh_family(self, user_id: int, fam: str | None, sid: str | None = None) -> None:
        try:
            if fam:
                await redis_client.setex(f"{_REFRESH_FAMILY_REVOKED_PREFIX}{fam}", _REFRESH_TTL, "1")
                if sid:
                    await redis_client.delete(f"{_REFRESH_SESSION_PREFIX}{sid}")
                return
            await redis_client.setex(f"{_REFRESH_REVOKED_PREFIX}{user_id}", _REFRESH_TTL, "1")
        except Exception as e:
            logger.warning("refresh: failed to revoke family for user %s: %s", user_id, e)

    async def get_me(self, user_id: int) -> User:
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        return user

    async def change_password(self, user: User, current_password: str, new_password: str) -> None:
        if not await verify_password_for_login_async(
            current_password, user.password_hash, oauth_provider=user.oauth_provider
        ):
            raise InvalidCredentials()

        user.password_hash = await hash_password_async(new_password)
        await self.db.commit()
        await self.db.refresh(user)
        await revoke_all_refresh_sessions(user.id)


async def _family_for_sid(sid: str) -> str | None:
    try:
        value = await redis_client.get(f"{_REFRESH_FAMILY_INDEX_PREFIX}{sid}")
        return value if isinstance(value, str) and value else None
    except Exception as e:
        logger.warning("refresh: could not resolve family for sid %s: %s", sid, e)
        return None


async def clear_refresh_family_revocation(user_id: int) -> None:
    try:
        await redis_client.delete(f"{_REFRESH_REVOKED_PREFIX}{user_id}")
    except Exception as e:
        logger.warning("refresh: failed to clear revocation flag for user %s: %s", user_id, e)


async def clear_refresh_revocation(user_id: int) -> None:
    try:
        await redis_client.delete(f"{_REFRESH_REVOKED_PREFIX}{user_id}")
    except Exception as e:
        logger.warning("refresh: failed to clear user revocation for user %s: %s", user_id, e)


async def store_refresh_session(refresh_token: str) -> None:
    try:
        payload = decode_token(refresh_token)
        sid = payload.get("sid")
        jti = payload.get("jti")
        fam = payload.get("fam")
        user_id = payload.get("sub")
        if not sid or not jti:
            return
        record = json.dumps(
            {
                "jti": jti,
                "prev_jti": None,
                "prev_at": 0,
                "fam": fam,
            }
        )
        await redis_client.setex(f"{_REFRESH_SESSION_PREFIX}{sid}", _REFRESH_TTL, record)
        if fam:
            await redis_client.setex(f"{_REFRESH_FAMILY_INDEX_PREFIX}{sid}", _REFRESH_TTL, fam)
        if user_id and sid:
            try:
                await redis_client.sadd(f"{_REFRESH_USER_SESSIONS_PREFIX}{user_id}", sid)
                await redis_client.expire(f"{_REFRESH_USER_SESSIONS_PREFIX}{user_id}", _REFRESH_TTL)
            except Exception:
                pass
    except Exception as e:
        logger.warning("refresh: failed to store session record: %s", e)
