from __future__ import annotations

import time

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.redis import redis_client
from src.core.security import decode_token
from src.errors import InvalidToken, TokenRevoked, UnauthorizedError, UserNotFound
from src.repositories.user_repository import UserRepository

_BLACKLIST_CACHE_TTL = 60
_blacklist_cache: dict[str, float] = {}

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    token = credentials.credentials

    now = time.time()
    cached = _blacklist_cache.get(token)
    if cached is not None and cached > now:
        raise TokenRevoked()
    if cached is None:
        try:
            is_blacklisted = await redis_client.get(f"jwt:blacklist:{token}")
            if is_blacklisted:
                _blacklist_cache[token] = now + _BLACKLIST_CACHE_TTL
                raise TokenRevoked()
        except TokenRevoked:
            raise
        except Exception:
            pass

    payload = decode_token(token)
    user_id = payload.get("sub")
    token_type = payload.get("type")
    if not user_id or token_type != "access":
        raise InvalidToken()

    user = await UserRepository(db).get(int(user_id))
    if not user:
        raise UserNotFound()
    return user


async def get_current_active_user(
    user=Depends(get_current_user),
):
    if not user.is_active:
        raise UnauthorizedError(detail="Account is deactivated.")
    return user
