from __future__ import annotations

import json

import pytest
import pytest_asyncio

from src.core.database import AsyncSessionLocal
from src.core.security import create_refresh_token, hash_password
from src.domains.auth.services.auth_service import AuthService
from src.domains.users.models.user import User, UserRole
from src.shared.errors import UserNotFound


class _FakeSessionStore:
    """In-memory fake for the Upstash REST adapter that models the refresh
    session-rotation record (current jti + previous jti) and the family-revoked
    marker, mirroring the server LUA script's semantics so the service control
    flow can be exercised in CI without a real Redis."""

    def __init__(self) -> None:
        self.records: dict[str, dict] = {}
        self.revoked: dict[str, str] = {}
        self.blacklist: dict[str, str] = {}

    async def get(self, key: str):
        if key.startswith("refresh:revoked:"):
            return self.revoked.get(key)
        if key.startswith("refresh:session:"):
            rec = self.records.get(key)
            return json.dumps(rec) if rec else None
        if key.startswith("jwt:blacklist:"):
            return self.blacklist.get(key)
        return None

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        if key.startswith("refresh:revoked:"):
            self.revoked[key] = value
        elif key.startswith("jwt:blacklist:"):
            self.blacklist[key] = value
        elif key.startswith("refresh:session:"):
            self.records[key] = json.loads(value)

    async def delete(self, key: str) -> None:
        self.records.pop(key, None)
        self.revoked.pop(key, None)

    async def eval(self, _script: str, _numkeys: int, *args):
        # args: session_key, presented_jti, new_jti, grace, ttl, now
        key, presented, new_jti, _grace, _ttl, _now = args
        rec = self.records.get(key)
        if rec is None:
            return -1
        if rec["jti"] == presented or rec.get("prev_jti") == presented:
            rec["prev_jti"] = rec["jti"]
            rec["jti"] = new_jti
            return 1
        return 0


@pytest_asyncio.fixture(autouse=True)
async def _create_tables():
    import src.models  # noqa: F401 — register all models
    from src.core.database import engine
    from src.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def fake_store(monkeypatch):
    import src.core.redis as redis_mod
    import src.domains.auth.services.auth_service as service_mod

    store = _FakeSessionStore()
    monkeypatch.setattr(redis_mod, "redis_client", store)
    monkeypatch.setattr(service_mod, "redis_client", store)
    return store


@pytest.mark.asyncio
async def test_refresh_rotates_across_multiple_uses(fake_store) -> None:
    """Regression: a session must survive MORE THAN ONE refresh. The previous
    one-shot family guard killed the session on the second rotation."""
    password = "TestPass123!"
    async with AsyncSessionLocal() as session:
        session.add(
            User(
                email="rotate@civicpulse.com",
                password_hash=hash_password(password),
                full_name="Rotate User",
                role=UserRole.field_worker,
                is_active=True,
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        svc = AuthService(session)
        _, r1 = await svc.login("rotate@civicpulse.com", password)

    # Multiple successive rotations must each succeed.
    for _ in range(3):
        async with AsyncSessionLocal() as session:
            svc = AuthService(session)
            _, r1 = await svc.refresh(r1)

    assert r1


@pytest.mark.asyncio
async def test_refresh_unknown_user_rejected(fake_store) -> None:
    refresh = create_refresh_token({"sub": "999999"})
    with pytest.raises(UserNotFound):
        async with AsyncSessionLocal() as session:
            svc = AuthService(session)
            await svc.refresh(refresh)


@pytest.mark.asyncio
async def test_replay_revokes_only_the_replayed_signin(fake_store) -> None:
    """A replayed token must end its own sign-in, not every device.

    Two logins for the same account are two independent families. Rotating the
    first out and then replaying its original token is a reuse signal and must
    kill *that* sign-in — but the second sign-in, on another device, must keep
    working. The old user-wide flag would have torn both down.
    """
    password = "TestPass123!"
    async with AsyncSessionLocal() as session:
        session.add(
            User(
                email="family@civicpulse.com",
                password_hash=hash_password(password),
                full_name="Family User",
                role=UserRole.field_worker,
                is_active=True,
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        svc = AuthService(session)
        _, device_a = await svc.login("family@civicpulse.com", password)
        _, device_b = await svc.login("family@civicpulse.com", password)

    # Device A rotates once: device_a is now the *previous* jti of its session.
    async with AsyncSessionLocal() as session:
        svc = AuthService(session)
        _, device_a2 = await svc.refresh(device_a)

    # Replay A's original token, past the grace window by clearing prev_jti.
    # Also drop the blacklist entry: a rotated-out token is normally refused at
    # the blacklist check, but the *rotation record* is the durable reuse signal
    # that must catch a token whose blacklist entry has lapsed. Clearing both
    # is what reaches the replay branch under test.
    fake_store.blacklist.clear()
    for key, rec in fake_store.records.items():
        rec["prev_at"] = 0
        rec["prev_jti"] = None

    async with AsyncSessionLocal() as session:
        svc = AuthService(session)
        with pytest.raises(Exception):
            await svc.refresh(device_a)

    # Device B never replayed anything and must still renew.
    async with AsyncSessionLocal() as session:
        svc = AuthService(session)
        _, device_b2 = await svc.refresh(device_b)
    assert device_b2

    # And the replayed sign-in stays dead.
    async with AsyncSessionLocal() as session:
        svc = AuthService(session)
        with pytest.raises(Exception):
            await svc.refresh(device_a2)
