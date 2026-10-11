import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable

from upstash_redis.asyncio import Redis as UpstashRedis

from src.core.config import settings

logger = logging.getLogger(__name__)


class UpstashRedisAdapter:
    def __init__(self, url: str, token: str):
        self._client = UpstashRedis(url=url, token=token)

    async def ping(self):
        return await self._client.ping()

    async def get(self, key: str):
        return await self._client.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        return await self._client.set(key, value, ex=ttl)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        """SET with the two options single-use markers depend on.

        The adapter previously exposed only `get`/`setex`/`delete`, so any
        caller reaching for `SET NX` — the atomic primitive that makes "first
        writer wins" possible — hit `AttributeError: UpstashRedisAdapter has
        no attribute 'set'`. Password-reset tokens and 2FA challenges were
        both written against it and failed open (caught and swallowed), so
        neither was ever actually marked consumed; this existed before those
        call sites and silently disabled them.

        `nx=True` makes the call return falsy when the key already exists,
        which is exactly the "someone else got here first" signal.
        """
        return await self._client.set(key, value, ex=ex, nx=nx)

    async def delete(self, key: str):
        return await self._client.delete(key)

    async def incr(self, key: str):
        return await self._client.incr(key)

    async def expire(self, key: str, ttl: int):
        return await self._client.expire(key, ttl)

    async def eval(self, script: str, numkeys: int, *args):
        cmd = ["EVAL", script, str(numkeys)] + list(args)
        return await self._client.execute(cmd)


def _build_redis_client() -> Any:
    """Pick the Redis backend from settings, once, at import time.

    The production path is Upstash REST — the app is compose/Render-deployed
    with UPSTASH_REDIS_REST_URL + _TOKEN set, and the adapter exposes the same
    method surface the rest of this module needs.

    When Upstash credentials are absent the client falls back to a plain Redis
    connection from REDIS_URL (see ADR-0005): a local `redis` container or any
    self-hosted Redis. `redis.asyncio.Redis` already speaks the same verbs
    (get/set/setex/ping/delete/incr/expire/eval), so the rest of this module is
    unchanged, and tests keep patching `redis_client` wholesale with fakeredis.
    """
    upstash_url = (settings.UPSTASH_REDIS_REST_URL or "").strip()
    upstash_token = (settings.UPSTASH_REDIS_REST_TOKEN or "").strip()
    if upstash_url and upstash_token:
        return UpstashRedisAdapter(url=upstash_url, token=upstash_token)

    from redis.asyncio import Redis as AsyncRedis

    return AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)


redis_client: Any = _build_redis_client()

_RETRY_DELAYS = [1, 2, 4, 8, 16]


async def init_redis():
    for attempt, delay in enumerate(_RETRY_DELAYS):
        try:
            await redis_client.ping()
            logger.info("Redis connected successfully.")
            return redis_client
        except Exception as e:
            logger.warning("Redis ping attempt %d failed: %s", attempt + 1, e)
            if attempt < len(_RETRY_DELAYS) - 1:
                await asyncio.sleep(delay)
            else:
                logger.error("Redis failed to connect after %d attempts", len(_RETRY_DELAYS))
                raise


RATE_LIMIT_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local current_time = tonumber(ARGV[3])
local requested = tonumber(ARGV[4] or 1)

local bucket = redis.call('HMGET', key, 'tokens', 'last_updated')
local tokens = tonumber(bucket[1])
local last_updated = tonumber(bucket[2])

if not tokens then
    tokens = capacity
    last_updated = current_time
else
    local delta = math.max(0, current_time - last_updated)
    tokens = math.min(capacity, tokens + delta * refill_rate)
end

local limited = 0
if tokens >= requested then
    tokens = tokens - requested
else
    limited = 1
end

redis.call('HMSET', key, 'tokens', tokens, 'last_updated', current_time)
redis.call('EXPIRE', key, 86400)

-- Return status plus the numbers a client needs to pace itself:
--   remaining tokens after this request, and seconds until the bucket is full
--   again. Both feed the X-RateLimit-* response headers.
local remaining = math.floor(tokens)
if remaining < 0 then remaining = 0 end
local reset = math.max(1, math.ceil((capacity - tokens) / refill_rate))
return {limited, remaining, reset}
"""


class RateLimitResult:
    """Outcome of one token-bucket consume, header-friendly.

    ``allowed`` is the decision; ``remaining``/``reset_seconds``/``limit`` are
    propagated to the caller as ``X-RateLimit-*``.
    """

    __slots__ = ("allowed", "remaining", "reset_seconds", "limit")

    def __init__(self, *, allowed: bool, remaining: int, reset_seconds: int, limit: int) -> None:
        self.allowed = allowed
        self.remaining = remaining
        self.reset_seconds = reset_seconds
        self.limit = limit


async def consume_rate_limit(key: str, capacity: int, refill_rate_per_sec: float) -> RateLimitResult:
    """Consume one token from ``key``'s bucket and report the decision + budget.

    Fails **open** (allows the request) when Redis is unreachable or a stub
    without Lua support is in place — a rate limiter that takes the API down
    when its own store is degraded is worse than the traffic it protects.
    """
    try:
        now = time.time()
        result = await redis_client.eval(
            RATE_LIMIT_BUCKET_LUA,
            1,
            key,
            str(capacity),
            str(refill_rate_per_sec),
            str(now),
            "1",
        )
        if isinstance(result, (list, tuple)) and len(result) >= 3:
            return RateLimitResult(
                allowed=int(result[0]) == 0,
                remaining=max(0, int(result[1])),
                reset_seconds=max(1, int(result[2])),
                limit=capacity,
            )
    except Exception as e:
        logger.error("Rate limit check failed for key %s: %s", key, e)

    # Stub Redis (no Lua) or a Redis outage: allow, with a full budget.
    return RateLimitResult(allowed=True, remaining=capacity, reset_seconds=1, limit=capacity)


async def check_rate_limit(key: str, capacity: int, refill_rate_per_sec: float) -> bool:
    """True when the request should be rejected. Thin wrapper over ``consume_rate_limit``."""
    result = await consume_rate_limit(key, capacity, refill_rate_per_sec)
    return not result.allowed


async def get_cached(key: str) -> Any | None:
    """Read a JSON value back out of the cache.

    Returned as `Any` rather than `dict | None` for the same reason
    :func:`set_cached` accepts `Any`: the cache stores whatever was written,
    lists included, and pretending otherwise only pushed the mismatch onto
    the caller.
    """
    try:
        data = await redis_client.get(key)
        if data:
            return json.loads(data)  # type: ignore[no-any-return]
        return None
    except Exception as e:
        logger.debug("Cache read failed for %s: %s", key, e)
        return None


async def set_cached(key: str, value: Any, ttl: int = 86400) -> None:
    """Cache an arbitrary JSON-serialisable value.

    Widened from `dict` because callers legitimately cache lists too (the
    heatmap endpoint caches a `list[dict]`, which does not satisfy `dict`) —
    the runtime behaviour was always `json.dumps`, so the narrower annotation
    was simply wrong.
    """
    try:
        await redis_client.setex(key, ttl, json.dumps(value))
    except Exception as e:
        logger.warning("Cache write failed for %s: %s", key, e)


async def delete_cached(key: str) -> None:
    try:
        await redis_client.delete(key)
    except Exception as e:
        logger.debug("Cache delete failed for %s: %s", key, e)


# Per-process in-flight map shared by get_cached_or_compute. A cache stampede
# (many concurrent requests for the same cold key) is a *per-process* concern
# here: one uvicorn worker holds one event loop, and the dashboard caches are
# read at the same instant by every client after an invalidation. Keys are
# removed in `finally`, so a crash in the factory cannot leak an entry.
_inflight: dict[str, "asyncio.Future[Any]"] = {}


async def get_cached_or_compute(key: str, ttl: int, factory: "Callable[[], Awaitable[Any]]") -> Any:
    """Cache-aside with a single-flight guard around ``factory``.

    Returns the cached value when present. Otherwise the first caller runs
    ``factory`` and stores the result; concurrent callers for the same key
    await that same result instead of each hammering the database — so a cold
    or just-invalidated key produces exactly one upstream computation rather
    than one per request.

    The guard is deliberately process-local: Redis would be the place for a
    cross-worker lock, but that adds a lock round-trip and its own failure
    modes to every read, and a single-deployment API does not need it.
    """
    cached = await get_cached(key)
    if cached is not None:
        return cached

    existing = _inflight.get(key)
    if existing is not None and not existing.done():
        # Someone is already computing this key; share their result.
        return await asyncio.shield(existing)

    loop = asyncio.get_running_loop()
    future: "asyncio.Future[Any]" = loop.create_future()
    _inflight[key] = future
    try:
        value = await factory()
        await set_cached(key, value, ttl=ttl)
        future.set_result(value)
        return value
    except BaseException as exc:  # surface the failure to every waiter
        if not future.done():
            future.set_exception(exc)
        raise
    finally:
        _inflight.pop(key, None)


async def check_redis_health() -> bool:
    try:
        await redis_client.ping()
        return True
    except Exception:
        return False
