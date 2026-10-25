from __future__ import annotations

import hashlib
import logging

from fastapi import Request

from src.core.client_ip import resolve_client_ip
from src.core.config import settings
from src.core.redis import consume_rate_limit
from src.shared.errors import RateLimitError

logger = logging.getLogger(__name__)

_AUTH_WINDOW_SECONDS = 60


def _account_key(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]


def _client_ip(request: Request) -> str:
    return resolve_client_ip(request)


async def enforce_auth_rate_limit(
    request: Request,
    *,
    action: str,
    per_ip: int,
    per_account: int | None = None,
    account: str | None = None,
) -> None:
    ips = [f"auth:{action}:ip:{_client_ip(request)}"]
    acct = _account_key(account)
    if acct and per_account is not None:
        ips.append(f"auth:{action}:acct:{acct}")

    for index, key in enumerate(ips):
        capacity = per_ip if index == 0 else int(per_account or per_ip)
        refill = capacity / _AUTH_WINDOW_SECONDS
        try:
            result = await consume_rate_limit(key, capacity, refill)
        except Exception as exc:
            logger.warning("auth rate limit unavailable for action %s: %s", action, exc)
            return
        if not result.allowed:
            raise RateLimitError("Too many authentication attempts. Please try again in a minute.")


def login_limits() -> tuple[int, int]:
    return settings.AUTH_LOGIN_RATE_LIMIT_IP, settings.AUTH_LOGIN_RATE_LIMIT_ACCOUNT


def refresh_limits() -> tuple[int, int]:
    return settings.AUTH_REFRESH_RATE_LIMIT_IP, settings.AUTH_REFRESH_RATE_LIMIT_ACCOUNT


def forgot_password_limits() -> tuple[int, int]:
    return settings.AUTH_FORGOT_RATE_LIMIT_IP, settings.AUTH_FORGOT_RATE_LIMIT_ACCOUNT
