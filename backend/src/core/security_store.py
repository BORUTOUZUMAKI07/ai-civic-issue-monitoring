"""Fail-closed adapter for Redis-backed security state.

Token revocation, refresh rotation and one-time token consumption are security
boundaries: if the store cannot record the operation, it must not be treated as
successful. Every helper here either completes against Redis or raises
:class:`SecurityStoreUnavailableError`, which the shared ``AppError`` handler maps to
503. Non-security bookkeeping (caches, session lists, rate limits) deliberately
stays fail-open elsewhere; this module is only for state whose loss would
enable a replay or keep a revoked credential alive.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from src.core import redis as redis_module
from src.shared.errors.base import AppError

logger = logging.getLogger("civicpulse")


class SecurityStoreUnavailableError(AppError):
    """The store backing a security operation could not be reached."""

    def __init__(self, operation: str = "security operation") -> None:
        super().__init__(
            detail="Security services are temporarily unavailable. Please retry.",
            status_code=503,
            error_code="SECURITY_UNAVAILABLE",
        )
        self.operation = operation


async def _guarded(operation: str, action: Callable[[], Awaitable[Any]]) -> Any:
    try:
        return await action()
    except SecurityStoreUnavailableError:
        raise
    except Exception as exc:
        logger.error("security store unavailable during %s: %s", operation, exc)
        raise SecurityStoreUnavailableError(operation) from exc


async def consume_one_time(key: str, ttl_seconds: int) -> bool:
    """Atomically claim a one-time token.

    Returns ``True`` when the token was already used. A store failure raises
    instead of returning ``False``, so a replay cannot slip through an outage.
    """
    was_new = await _guarded(
        "one-time token consumption",
        lambda: redis_module.redis_client.set(key, "1", ex=ttl_seconds, nx=True),
    )
    return not bool(was_new)


async def mark_revoked(key: str, ttl_seconds: int) -> None:
    await _guarded("revocation", lambda: redis_module.redis_client.setex(key, ttl_seconds, "1"))


async def delete_keys(*keys: str) -> None:
    """Delete keys one by one; any failure fails the whole operation."""
    for key in keys:
        await _guarded("session cleanup", lambda: redis_module.redis_client.delete(key))


async def blacklist_jti(jti: str, ttl_seconds: int) -> None:
    await _guarded(
        "token blacklisting",
        lambda: redis_module.redis_client.setex(f"jwt:blacklist:{jti}", ttl_seconds, "1"),
    )


async def is_blacklisted(jti: str) -> bool:
    """Strict blacklist read: a store failure is reported, not treated as clean."""
    result = await _guarded("blacklist check", lambda: redis_module.redis_client.get(f"jwt:blacklist:{jti}"))
    return result is not None


async def is_revoked(*keys: str) -> bool:
    """True if any key carries a revocation marker; store failure raises."""
    for key in keys:
        result = await _guarded("revocation check", lambda: redis_module.redis_client.get(key))
        if result:
            return True
    return False


async def store_session(key: str, record: str, ttl_seconds: int) -> None:
    await _guarded("session storage", lambda: redis_module.redis_client.setex(key, ttl_seconds, record))


async def rotate_session(script: str, numkeys: int, *args: Any) -> int:
    result = await _guarded("session rotation", lambda: redis_module.redis_client.eval(script, numkeys, *args))
    return int(result)


async def read_key(key: str) -> Any:
    return await _guarded("security state read", lambda: redis_module.redis_client.get(key))
