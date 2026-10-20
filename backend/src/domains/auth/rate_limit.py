"""Auth-specific rate limiting.

The global :class:`~src.middleware.rate_limit.RateLimitMiddleware` applies one
per-IP and one per-user budget to *every* request. That is a good general
circuit-breaker, but it is the wrong shape for credential endpoints:

* ``/auth/login`` runs **before** there is any identity, so the generic per-user
  bucket never applies, and the generic per-IP bucket (60 burst, 1/s refill) is
  far too generous to slow down password guessing.
* Nothing keys on the *account being attacked*. A botnet spraying one password
  across a thousand addresses, or stuffing one mailbox from many IPs, stays
  under every per-IP cap while concentrating all its attempts on one account.

So the endpoints that check or mint credentials get a second, tighter budget —
per client IP *and* per account — on top of the global one. The account key is a
SHA-256 of the normalised identifier, never the raw email, so Redis holds no
addresses (matching the project's "no PII in keys" stance).
"""

from __future__ import annotations

import hashlib
import logging

from fastapi import Request

from src.core.config import settings
from src.core.redis import consume_rate_limit
from src.shared.errors import RateLimitError

logger = logging.getLogger(__name__)

# One minute is the natural window for "tries per minute" and lets a client
# recover on its own without an operator unblocking anyone.
_AUTH_WINDOW_SECONDS = 60


def _account_key(value: str | None) -> str | None:
    """Hash an account identifier so no raw email reaches a Redis key.

    ``None`` when there is nothing to key on, so the per-account bucket is
    skipped rather than collapsing every anonymous caller onto a single key and
    rate-limiting the world together.
    """
    if not value:
        return None
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]


def _client_ip(request: Request) -> str:
    """The caller's address, as the global middleware already resolves it.

    Deliberately *not* reading ``X-Forwarded-For``: without a configured trusted
    proxy, honouring it lets any caller mint a fresh rate-limit key per request
    by spoofing a hop, which silently disables the limiter. Adding proxy trust
    is a deployment decision (a trusted-IP list), not something this helper
    should assume.
    """
    return request.client.host if request.client else "unknown"


async def enforce_auth_rate_limit(
    request: Request,
    *,
    action: str,
    per_ip: int,
    per_account: int | None = None,
    account: str | None = None,
) -> None:
    """Apply the per-IP and per-account windows for one auth action.

    ``per_ip`` is the number of attempts allowed in the window per source
    address; ``per_account`` (when the action carries an account identifier) is
    the cap for a single account regardless of how many addresses it is tried
    from. Both are consumed for every attempt — the account cap being a *second*
    key, not a fallback — so neither a single noisy address nor a distributed
    attack on one account slips through.

    Fails **open** on a Redis outage, exactly like the global middleware: taking
    the login endpoint down because the limiter's own store is degraded is worse
    than the traffic it would have throttled. The failure is logged so the
    outage is still visible.
    """
    # Token-bucket capacity/refill derived from "N per minute": capacity is the
    # burst size and the refill is the steady state, so a caller can spend the
    # whole budget at once (a human retrying a typo) but cannot sustain it.
    ips = [f"auth:{action}:ip:{_client_ip(request)}"]
    acct = _account_key(account)
    if acct and per_account is not None:
        ips.append(f"auth:{action}:acct:{acct}")

    for index, key in enumerate(ips):
        capacity = per_ip if index == 0 else int(per_account or per_ip)
        refill = capacity / _AUTH_WINDOW_SECONDS
        try:
            result = await consume_rate_limit(key, capacity, refill)
        except Exception as exc:  # noqa: BLE001 — see the fail-open note
            logger.warning("auth rate limit unavailable for action %s: %s", action, exc)
            return
        if not result.allowed:
            raise RateLimitError("Too many authentication attempts. Please try again in a minute.")


def login_limits() -> tuple[int, int]:
    """Per-IP / per-account caps for ``/auth/login`` (and 2FA verify)."""
    return settings.AUTH_LOGIN_RATE_LIMIT_IP, settings.AUTH_LOGIN_RATE_LIMIT_ACCOUNT


def refresh_limits() -> tuple[int, int]:
    """Per-IP / per-account caps for ``/auth/refresh``."""
    return settings.AUTH_REFRESH_RATE_LIMIT_IP, settings.AUTH_REFRESH_RATE_LIMIT_ACCOUNT


def forgot_password_limits() -> tuple[int, int]:
    """Per-IP / per-account caps for ``/auth/forgot-password``."""
    return settings.AUTH_FORGOT_RATE_LIMIT_IP, settings.AUTH_FORGOT_RATE_LIMIT_ACCOUNT
