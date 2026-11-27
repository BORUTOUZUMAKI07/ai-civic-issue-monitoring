from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import redis as redis_module
from src.core.config import settings
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password_async,
    verify_password_for_login_async,
)
from src.core.security_store import (
    SecurityStoreUnavailableError,
    blacklist_jti,
    delete_keys,
    is_blacklisted,
    is_revoked,
    mark_revoked,
    read_key,
    rotate_session,
    store_session,
)
from src.domains.auth.password_reset import revoke_all_refresh_sessions
from src.domains.users.models.user import User, UserRole
from src.domains.users.repositories.user_repository import UserRepository
from src.shared.errors import (
    EmailAlreadyExists,
    EmailNotVerified,
    InvalidCredentials,
    InvalidToken,
    RefreshTokenReuse,
    TokenExpired,
    TokenRevoked,
    UnauthorizedError,
    UserNotFound,
)

logger = logging.getLogger("civicpulse")


def _decode_for_revocation(token: str) -> dict[str, Any] | None:
    """Return usable claims, or None for an expired/malformed token.

    Kept out of ``logout`` so the loop never has an ``except: continue``
    (Bandit B112): revocation should skip an unusable token and still process
    the other half of the pair.
    """
    try:
        return decode_token(token)
    except (InvalidToken, TokenExpired):
        return None


_REFRESH_SESSION_PREFIX = "refresh:session:"
_REFRESH_REVOKED_PREFIX = "refresh:revoked:"
_REFRESH_FAMILY_REVOKED_PREFIX = "refresh:revoked:family:"
_REFRESH_FAMILY_INDEX_PREFIX = "refresh:family:"
_REFRESH_USER_SESSIONS_PREFIX = "refresh:user:sessions:"
_REFRESH_TTL = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400


def _reuse_grace_seconds() -> int:
    """Read at call time so config overrides in tests/deployments are honoured."""
    return max(0, int(settings.REFRESH_REUSE_GRACE_SECONDS))


class _RedisClientProxy:
    """Resolve Redis client dynamically.

    - If tests patch ``auth_service.redis_client`` directly, that override wins.
    - Otherwise delegate to the live ``src.core.redis.redis_client`` so fixtures
      that patch the core module (fakeredis) are respected.
    """

    def __getattr__(self, name: str) -> Any:
        mod = sys.modules[__name__]
        client = mod.__dict__.get("redis_client")
        if client is self or client is None:
            client = redis_module.redis_client
        return getattr(client, name)


redis_client: Any = _RedisClientProxy()

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
        requires_verification = bool(getattr(settings, "EMAIL_VERIFICATION_REQUIRED", False))
        user = User(
            email=email,
            password_hash=await hash_password_async(password),
            full_name=full_name,
            role=user_role,
            email_verified=not requires_verification,
            email_verified_at=None,
        )
        created = await self.user_repo.create(user)
        if requires_verification:
            try:
                from src.domains.auth.email_verification import send_verification_email

                await send_verification_email(self.db, created)
            except Exception:
                logger.warning("register: failed to send verification email for user %s", created.id)
        return created

    async def login(self, email: str, password: str) -> tuple[str, str]:
        user = await self.user_repo.get_by_email(email)
        if not user or not await verify_password_for_login_async(
            password, user.password_hash, oauth_provider=user.oauth_provider
        ):
            raise InvalidCredentials()
        if not user.is_active:
            raise UnauthorizedError(detail="Account is deactivated.")
        if getattr(settings, "EMAIL_VERIFICATION_REQUIRED", False) and not getattr(user, "email_verified", True):
            raise EmailNotVerified()

        # Session state is a security boundary: if Redis cannot clear a stale
        # revocation or record the new session, refuse to issue credentials that
        # could neither be revoked nor refreshed.
        await clear_user_revocation(user.id)
        refresh_token = create_refresh_token({"sub": str(user.id)})
        await store_refresh_session(refresh_token)

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
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

        if jti and await is_blacklisted(jti):
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
                # Outside the grace window this is theft, not a racing tab.
                # The switch exists for operators who need strict single-use
                # without tearing down every device in the family; the default
                # keeps the blast radius confined to this sign-in.
                if bool(settings.REFRESH_REVOKE_ON_REUSE):
                    await self._revoke_refresh_family(user.id, fam, sid)
                raise RefreshTokenReuse()
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
        keys = [f"{_REFRESH_REVOKED_PREFIX}{user_id}"]
        if fam:
            keys.append(f"{_REFRESH_FAMILY_REVOKED_PREFIX}{fam}")
        # A failed read must not be read as "not revoked"; is_revoked raises
        # SecurityStoreUnavailableError so no replacement token is minted.
        return await is_revoked(*keys)

    async def _rotate_refresh_session(self, sid: str, jti: str, new_jti: str) -> int:
        return await rotate_session(
            _ROTATE_REFRESH_LUA,
            1,
            f"{_REFRESH_SESSION_PREFIX}{sid}",
            jti,
            new_jti,
            str(_reuse_grace_seconds()),
            str(_REFRESH_TTL),
            str(int(time.time())),
        )

    async def _blacklist_best_effort(self, jti: str, ttl_seconds: int) -> None:
        # Kept as a method for call-site readability, but no longer best-effort:
        # a rotated token that is not blacklisted stays valid and would let the
        # old credential live on during an outage.
        await blacklist_jti(jti, ttl_seconds)

    async def logout(self, refresh_token: Optional[str], access_token: Optional[str] = None) -> None:
        failed = False
        for token in (access_token, refresh_token):
            if not token:
                continue
            payload = _decode_for_revocation(token)
            if payload is None:
                # An expired/malformed token has nothing to revoke; the other
                # token in the pair is still processed below.
                continue
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                ttl = int(exp) - int(time.time())
                if ttl > 0:
                    try:
                        await blacklist_jti(jti, ttl)
                    except SecurityStoreUnavailableError:
                        failed = True
            sid = payload.get("sid")
            if sid:
                try:
                    await self._revoke_session(sid, payload.get("fam"))
                except SecurityStoreUnavailableError:
                    failed = True
        if failed:
            # Report the outage rather than telling the user they are signed out
            # when their credentials are still live.
            raise SecurityStoreUnavailableError("logout")

    async def _revoke_session(self, sid: str, fam: str | None) -> None:
        await delete_keys(f"{_REFRESH_SESSION_PREFIX}{sid}")
        resolved_fam = fam or await _family_for_sid(sid)
        if resolved_fam:
            await mark_revoked(f"{_REFRESH_FAMILY_REVOKED_PREFIX}{resolved_fam}", _REFRESH_TTL)
            await delete_keys(f"{_REFRESH_FAMILY_INDEX_PREFIX}{sid}")

    async def _revoke_refresh_family(self, user_id: int, fam: str | None, sid: str | None = None) -> None:
        if fam:
            await mark_revoked(f"{_REFRESH_FAMILY_REVOKED_PREFIX}{fam}", _REFRESH_TTL)
            if sid:
                await delete_keys(f"{_REFRESH_SESSION_PREFIX}{sid}")
            return
        await mark_revoked(f"{_REFRESH_REVOKED_PREFIX}{user_id}", _REFRESH_TTL)

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
    value = await read_key(f"{_REFRESH_FAMILY_INDEX_PREFIX}{sid}")
    return value if isinstance(value, str) and value else None


async def clear_user_revocation(user_id: int) -> None:
    """Single implementation for clearing a user-wide revocation marker.

    Previously two identically-behaving helpers existed and were called in
    sequence on every issuance path; one canonical function removes the drift
    and keeps the fail-closed behaviour in one place.
    """
    await delete_keys(f"{_REFRESH_REVOKED_PREFIX}{user_id}")


async def store_refresh_session(refresh_token: str) -> None:
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
    # The session record is what makes rotation and revocation possible — it
    # must be written or issuance fails. The per-user index only powers the
    # "list sessions" view, so it stays best-effort.
    await store_session(f"{_REFRESH_SESSION_PREFIX}{sid}", record, _REFRESH_TTL)
    if fam:
        await store_session(f"{_REFRESH_FAMILY_INDEX_PREFIX}{sid}", fam, _REFRESH_TTL)
    if user_id and sid:
        try:
            await redis_client.sadd(f"{_REFRESH_USER_SESSIONS_PREFIX}{user_id}", sid)
            await redis_client.expire(f"{_REFRESH_USER_SESSIONS_PREFIX}{user_id}", _REFRESH_TTL)
        except Exception:  # nosec B110 - session index update is best-effort
            pass
