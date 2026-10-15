"""Seed a field-worker account for the Locust load-test suite (CI gate).

The Locust suite (``backend/scripts/loadtest/locustfile.py``) only exercises
``/health`` unless ``LOCUST_EMAIL``/``LOCUST_PASSWORD`` are set. This script
inserts a real account through the app's own models + password hashing, so the
CI load gate can exercise the authenticated read paths (``/issues``,
``/dashboard/*``, ``/issues/search``) against real Postgres.

Usage (from ``backend/``, after the server reports healthy):

    python scripts/loadtest/seed_user.py

Configuration (env vars):

* ``SEED_EMAIL``     — default ``loadtest@example.com``
* ``SEED_PASSWORD``  — default ``LoadTest!2026`` (CI-local throwaway only)
* ``SEED_FULL_NAME`` — default ``Load Test User``

Idempotent: re-running updates the existing account's password/full-name
instead of failing on the unique email.
"""
from __future__ import annotations

import asyncio
import os

DEFAULT_EMAIL = "loadtest@example.com"
DEFAULT_PASSWORD = "LoadTest!2026"


async def main() -> int:
    email = os.getenv("SEED_EMAIL", DEFAULT_EMAIL)
    password = os.getenv("SEED_PASSWORD", DEFAULT_PASSWORD)
    full_name = os.getenv("SEED_FULL_NAME", "Load Test User")

    from sqlalchemy import select

    import src.models  # noqa: F401 — register every ORM model on Base.metadata
    from src.core.database import AsyncSessionLocal, init_db
    from src.core.security import hash_password_async
    from src.domains.users.models.user import User, UserRole

    # Creates tables in non-production environments (CI runs with
    # ENVIRONMENT=development). Production deployments use Alembic.
    if not await init_db():
        print("[seed_user] init_db() failed — is the database reachable?", flush=True)
        return 1

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        password_hash = await hash_password_async(password)
        if user is None:
            user = User(
                email=email,
                full_name=full_name,
                role=UserRole.field_worker,
                password_hash=password_hash,
                is_active=True,
            )
            session.add(user)
            action = "created"
        else:
            user.full_name = full_name
            user.password_hash = password_hash
            user.is_active = True
            action = "updated"
        await session.commit()
        print(f"[seed_user] account {email} {action} (id={user.id})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))