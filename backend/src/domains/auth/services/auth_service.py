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
        if not user or not await verify_password_for_login_async(
            password, user.password_hash, oauth_provider=user.oauth_provider
        ):
            raise InvalidCredentials()
        if not user.is_active:
            raise UnauthorizedError(detail="Account is deactivated.")

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        # A completed password login lifts the post-replay refresh lockout —
        # otherwise a single replayed token locked the account out of /refresh
        # for 7 days with no way back in.
        await clear_refresh_family_revocation(user.id)
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
        if not user_id:
            # `sub` is what ties a refresh token to an account. Silently
            # treating a missing one as user 0 (or letting `int(None)` raise
            # a TypeError out as a 500) is worse than rejecting the token.
            raise InvalidToken()
        user = await self.user_repo.get(int(str(user_id)))
        if not user:
            raise UserNotFound()

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})

        if sid and jti:
            if await self._refresh_family_revoked(user.id):
                raise TokenRevoked()
            new_refresh = create_refresh_token({"sub": str(user.id)}, sid=sid)
            new_jti = decode_token(new_refresh).get("jti", "")
            result = await self._rotate_refresh_session(sid, jti, new_jti)
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
                    await self._blacklist_best_effort(jti, ttl)

        return access_token, new_refresh

    async def _refresh_family_revoked(self, user_id: int) -> bool:
        """Read the post-replay lockout flag for ``user_id``.

        Fails open (``False``) when Redis is unreachable — the flag is a
        revocation signal, and an outage must not turn every refresh into a
        500. This matches the rest of the module, whose Redis usage is already
        best-effort.
        """
        try:
            return bool(await redis_client.get(f"{_REFRESH_REVOKED_PREFIX}{user_id}"))
        except Exception as e:
            logger.warning("refresh: Redis unavailable, treating family as not revoked: %s", e)
            return False

    async def _rotate_refresh_session(self, sid: str, jti: str, new_jti: str) -> int:
        """Run the rotation/reuse-detection script: 1 ok / 0 replay / -1 no record.

        Redis is the session store behind rotation, and both Redis calls used
        to sit here unguarded. The ``/auth/refresh`` route only catches
        ``AppError``, so a Redis outage surfaced as a raw exception and every
        session renewal returned a 500 — an instance that was otherwise serving
        traffic correctly logged every user out. Every other Redis-backed
        behaviour in this module already fails open; refresh now does too.

        Failing open cannot be escalated into a privilege gain: reuse detection
        is purely defensive, and whoever can reach Redis can already forge the
        state it checks. When Redis returns, the next successful rotation
        re-anchors the session record.
        """
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
        """Blacklist a rotated-out token, tolerating Redis being unreachable."""
        try:
            await blacklist_token(jti, ttl_seconds)
        except Exception as e:
            logger.warning("refresh: Redis unavailable, could not blacklist rotated token: %s", e)

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

    async def change_password(self, user: User, current_password: str, new_password: str) -> None:
        """Rotate a user's password after proving knowledge of the current one.

        Mirrors the reset flow: the new hash is written, then every refresh
        session for the account is revoked so a stolen refresh cookie cannot
        outlive the password change. Argon2 verification and hashing are both
        offloaded to a thread, as login and reset already do, so a burst of
        changes cannot stall the event loop.
        """
        if not await verify_password_for_login_async(
            current_password, user.password_hash, oauth_provider=user.oauth_provider
        ):
            raise InvalidCredentials()

        user.password_hash = await hash_password_async(new_password)
        await self.db.commit()
        await self.db.refresh(user)
        await revoke_all_refresh_sessions(user.id)


async def clear_refresh_family_revocation(user_id: int) -> None:
    """Lift the post-replay lockout once the user has re-authenticated.

    ``refresh:revoked:{user_id}`` is set when a replayed refresh token is
    detected and gates *every* future refresh for that user — but it was never
    cleared anywhere, so one replay left the account permanently unable to
    refresh for the full 7-day TTL, with no recovery path short of waiting it
    out. Since the flag's job is "no session survives the compromise signal",
    a fresh interactive login is exactly the event that should lift it: the
    user has just proven control of their credentials, and any session that
    existed before is moot because they are starting a new one.

    Best-effort, matching the rest of this module: if Redis is unreachable the
    login still succeeds and the flag ages out on its own TTL.
    """
    try:
        await redis_client.delete(f"{_REFRESH_REVOKED_PREFIX}{user_id}")
    except Exception as e:
        logger.warning("refresh: failed to clear revocation flag for user %s: %s", user_id, e)


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
