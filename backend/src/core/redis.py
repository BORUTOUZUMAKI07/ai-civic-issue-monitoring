import asyncio
import json
import logging
import time

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

    async def delete(self, key: str):
        return await self._client.delete(key)

    async def incr(self, key: str):
        return await self._client.incr(key)

    async def expire(self, key: str, ttl: int):
        return await self._client.expire(key, ttl)

    async def eval(self, script: str, numkeys: int, *args):
        cmd = ["EVAL", script, str(numkeys)] + list(args)
        return await self._client.execute(cmd)


redis_client: UpstashRedisAdapter = UpstashRedisAdapter(
    url=settings.UPSTASH_REDIS_REST_URL or "",
    token=settings.UPSTASH_REDIS_REST_TOKEN or "",
)

_RETRY_DELAYS = [1, 2, 4, 8, 16]


async def init_redis():
    for attempt, delay in enumerate(_RETRY_DELAYS):
        try:
            await redis_client.ping()
            logger.info("Redis (Upstash REST) connected successfully.")
            return redis_client
        except Exception as e:
            logger.warning("Redis ping attempt %d failed: %s", attempt + 1, e)
            if attempt < len(_RETRY_DELAYS) - 1:
                await asyncio.sleep(delay)
            else:
                logger.error("Redis failed to connect after %d attempts", len(_RETRY_DELAYS))
                raise


TOKEN_BUCKET_LUA = """
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

if tokens >= requested then
    tokens = tokens - requested
    redis.call('HMSET', key, 'tokens', tokens, 'last_updated', current_time)
    redis.call('EXPIRE', key, 86400)
    return 1
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_updated', current_time)
    redis.call('EXPIRE', key, 86400)
    return 0
end
"""


async def check_rate_limit(key: str, capacity: int, refill_rate_per_sec: float) -> bool:
    try:
        now = time.time()
        result = await redis_client.eval(
            TOKEN_BUCKET_LUA,
            1,
            key,
            str(capacity),
            str(refill_rate_per_sec),
            str(now),
            "1",
        )
        return result == 0  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Rate limit check failed for key %s: %s", key, e)
        return False


async def get_cached(key: str) -> dict | None:
    try:
        data = await redis_client.get(key)
        if data:
            return json.loads(data)  # type: ignore[no-any-return]
        return None
    except Exception as e:
        logger.debug("Cache read failed for %s: %s", key, e)
        return None


async def set_cached(key: str, value: dict, ttl: int = 86400) -> None:
    try:
        await redis_client.setex(key, ttl, json.dumps(value))
    except Exception as e:
        logger.warning("Cache write failed for %s: %s", key, e)


async def delete_cached(key: str) -> None:
    try:
        await redis_client.delete(key)
    except Exception as e:
        logger.debug("Cache delete failed for %s: %s", key, e)


async def check_redis_health() -> bool:
    try:
        await redis_client.ping()
        return True
    except Exception:
        return False
