"""Regression tests for the 2FA challenge consumption ordering.

The endpoint used to burn the challenge *before* checking the TOTP code, so a
single mistyped digit destroyed a valid challenge and forced a full re-login.
It now verifies first and burns second. Both halves of the contract are
load-bearing and both are tested here:

* a wrong code must NOT consume the challenge — the user retries with the
  correct one and still gets in;
* a successful verification MUST consume it — a replayed challenge (stolen
  from a log or trace) can never mint a second session.

The challenge is a real signed JWT from ``create_2fa_challenge_token``, and the
user is a real row with 2FA enabled and a known TOTP secret, so these exercise
the same code path as production rather than a mock of it.
"""

from __future__ import annotations

import pytest
import pyotp
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal
from src.core.security import create_2fa_challenge_token
from src.models.user import User, UserRole

VERIFY_URL = "/api/v1/auth/2fa/verify"

# A fixed base32 secret so the TOTP code is reproducible inside the test.
TOTP_SECRET = pyotp.random_base32()


@pytest.fixture
async def two_factor_user(db_engine):
    """Create a user with 2FA enabled and return their id + secret."""
    from src.core.security import hash_password_async

    async with AsyncSessionLocal() as session:
        user = User(
            email="2fa@civicpulse.com",
            password_hash=await hash_password_async("SomePass123!"),
            full_name="Two Factor",
            role=UserRole.field_worker,
            is_active=True,
            two_factor_enabled=True,
            totp_secret=TOTP_SECRET,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    yield user_id, TOTP_SECRET

    async with AsyncSessionLocal() as session:
        found = await session.get(User, user_id)
        if found:
            await session.delete(found)
            await session.commit()


def _valid_code(secret: str) -> str:
    return pyotp.TOTP(secret).now()


async def test_wrong_code_does_not_burn_the_challenge(client, two_factor_user) -> None:
    """The core fix: a mistyped digit leaves the challenge usable.

    Before the fix this sequence failed at the second step — the wrong code
    had already consumed the challenge, so the correct code was rejected with
    an invalid-token error and the user was forced to start over.
    """
    user_id, secret = two_factor_user
    challenge = create_2fa_challenge_token(user_id)

    # Step 1: a wrong code is rejected...
    bad = await client.post(VERIFY_URL, json={"challenge": challenge, "code": "000000"})
    assert bad.status_code in (401, 422), bad.text

    # Step 2: ...and the SAME challenge still works with the right code.
    good = await client.post(VERIFY_URL, json={"challenge": challenge, "code": _valid_code(secret)})
    assert good.status_code == 200, good.text


async def test_challenge_is_single_use_after_success(client, two_factor_user) -> None:
    """A successful verification burns the challenge: replay must fail."""
    user_id, secret = two_factor_user
    challenge = create_2fa_challenge_token(user_id)

    first = await client.post(VERIFY_URL, json={"challenge": challenge, "code": _valid_code(secret)})
    assert first.status_code == 200, first.text

    # Same challenge, still-valid TOTP code: must be refused.
    replay = await client.post(VERIFY_URL, json={"challenge": challenge, "code": _valid_code(secret)})
    assert replay.status_code == 401, replay.text


async def test_challenge_is_typed_and_scoped(client, two_factor_user) -> None:
    """An access token is not a challenge: the type check must reject it."""
    user_id, _ = two_factor_user
    from src.core.security import create_access_token

    access = create_access_token({"sub": str(user_id), "role": "field_worker"})
    res = await client.post(VERIFY_URL, json={"challenge": access, "code": "000000"})
    assert res.status_code == 401, res.text


async def test_wrong_code_twice_then_correct_code(client, two_factor_user) -> None:
    """Repeated typos never burn it either — only success does."""
    user_id, secret = two_factor_user
    challenge = create_2fa_challenge_token(user_id)

    for _ in range(3):
        res = await client.post(VERIFY_URL, json={"challenge": challenge, "code": "111111"})
        assert res.status_code in (401, 422), res.text

    good = await client.post(VERIFY_URL, json={"challenge": challenge, "code": _valid_code(secret)})
    assert good.status_code == 200, good.text
