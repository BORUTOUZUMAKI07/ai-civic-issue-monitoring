"""Unit tests for the auth-specific rate limiter.

The limiter's job is a policy decision — *which* buckets a credential endpoint
consults and what happens when each is exhausted — so it is exercised directly
with a fake ``consume_rate_limit`` rather than through the HTTP stack. That
keeps the test about the policy, not about whether fakeredis implements Lua.

The behaviours pinned here are the ones an attacker would notice if they
regressed:

* login consumes a per-IP bucket *and* a per-account bucket, so a distributed
  attempt on one account is still capped;
* the account key is a hash, never the raw email;
* an exhausted bucket raises ``RateLimitError`` (429);
* a Redis outage fails **open** (the endpoint stays up), matching the global
  middleware.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from src.core.redis import RateLimitResult
from src.domains.auth import rate_limit as rl
from src.shared.errors import RateLimitError


def _request(host: str = "203.0.113.7") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": [],
        "client": (host, 12345),
    }
    return Request(scope)


class _Recorder:
    """Fake ``consume_rate_limit`` that records every key and can deny chosen ones."""

    def __init__(self, deny: set[str] | None = None, boom: bool = False) -> None:
        self.keys: list[str] = []
        self.deny = deny or set()
        self.boom = boom

    async def __call__(self, key: str, capacity: int, refill: float) -> RateLimitResult:
        if self.boom:
            raise RuntimeError("redis down")
        self.keys.append(key)
        allowed = key not in self.deny
        return RateLimitResult(allowed=allowed, remaining=1, reset_seconds=60, limit=capacity)


@pytest.fixture
def patched(monkeypatch):
    def _install(recorder: _Recorder) -> _Recorder:
        monkeypatch.setattr(rl, "consume_rate_limit", recorder)
        return recorder

    return _install


@pytest.mark.asyncio
async def test_login_consumes_ip_and_account_buckets(patched) -> None:
    rec = patched(_Recorder())
    await rl.enforce_auth_rate_limit(
        _request(), action="login", per_ip=10, per_account=5, account="User@Example.com"
    )
    assert any(k.startswith("auth:login:ip:203.0.113.7") for k in rec.keys)
    assert any(k.startswith("auth:login:acct:") for k in rec.keys)
    assert len(rec.keys) == 2


@pytest.mark.asyncio
async def test_account_key_is_hashed_not_raw_email(patched) -> None:
    rec = patched(_Recorder())
    await rl.enforce_auth_rate_limit(
        _request(), action="login", per_ip=10, per_account=5, account="User@Example.com"
    )
    joined = " ".join(rec.keys)
    assert "user@example.com" not in joined.lower()
    assert "User@Example.com" not in joined


@pytest.mark.asyncio
async def test_account_bucket_case_insensitive(patched) -> None:
    """The same mailbox in different casing must hit one account bucket."""
    rec = patched(_Recorder())
    await rl.enforce_auth_rate_limit(
        _request(), action="login", per_ip=10, per_account=5, account="User@Example.com"
    )
    await rl.enforce_auth_rate_limit(
        _request(), action="login", per_ip=10, per_account=5, account="user@example.com"
    )
    acct_keys = [k for k in rec.keys if ":acct:" in k]
    assert len(acct_keys) == 2
    assert acct_keys[0] == acct_keys[1]


@pytest.mark.asyncio
async def test_denied_account_bucket_raises(patched) -> None:
    # Deny the account bucket; the IP bucket is consumed first and allowed.
    rec = patched(_Recorder(deny={"auth:login:acct:" + rl._account_key("user@example.com")}))
    with pytest.raises(RateLimitError):
        await rl.enforce_auth_rate_limit(
            _request(), action="login", per_ip=10, per_account=5, account="user@example.com"
        )
    assert rec.keys  # the IP bucket was still consumed


@pytest.mark.asyncio
async def test_no_account_means_ip_bucket_only(patched) -> None:
    rec = patched(_Recorder())
    await rl.enforce_auth_rate_limit(_request(), action="forgot", per_ip=5, per_account=3, account=None)
    assert len(rec.keys) == 1
    assert ":acct:" not in rec.keys[0]


@pytest.mark.asyncio
async def test_redis_outage_fails_open(patched) -> None:
    """A degraded limiter must not take the login endpoint down."""
    patched(_Recorder(boom=True))
    # No exception → the request would proceed.
    await rl.enforce_auth_rate_limit(
        _request(), action="login", per_ip=10, per_account=5, account="user@example.com"
    )
