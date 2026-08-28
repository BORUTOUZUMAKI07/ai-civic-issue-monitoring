from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import decode_token, is_token_blacklisted
from src.errors import InvalidToken, TokenRevoked, UnauthorizedError, UserNotFound
from src.repositories.user_repository import UserRepository


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = _extract_token(request)
    if not token:
        raise UnauthorizedError(detail="Not authenticated")

    payload = decode_token(token)

    jti = payload.get("jti")
    if jti and await is_token_blacklisted(jti):
        raise TokenRevoked()

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
