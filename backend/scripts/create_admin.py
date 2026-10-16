"""Create (or promote) the first admin account — the deployment bootstrap.

The public API can only register ``field_worker``/``viewer`` accounts
(``src/domains/auth/api/routes.py``), the OAuth flow also lands users as
``field_worker``, and promoting anyone to ``admin`` requires an existing
``super_admin`` (``src/domains/users/services/user_service.py``). A brand-new
database therefore has no route into the admin console — the review queue, user
management, engineer roster and ML endpoints are all unreachable. This script is
the one supported way in: it inserts a user directly through the app's own models
and password hashing, exactly like ``scripts/loadtest/seed_user.py``.

Usage (from ``backend/``, with the database reachable):

    ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='<at-least-12-chars>' \
        python scripts/create_admin.py

Configuration (env vars):

* ``ADMIN_EMAIL``     — required; the login email.
* ``ADMIN_PASSWORD``  — required; at least 12 chars, not a well-known placeholder.
* ``ADMIN_FULL_NAME`` — optional; defaults to ``CivicPulse Admin``.
* ``ADMIN_ROLE``      — optional; ``admin`` (default) or ``super_admin``.

Idempotent: re-running promotes/updates the existing account instead of failing
on the unique email. When the account is created/updated it is also unbound from
any OAuth identity and activated, so the password actually works for login.
"""

from __future__ import annotations

import asyncio
import os

MIN_PASSWORD_LENGTH = 12
VALID_ROLES = ("admin", "super_admin")

# Passwords that appear in templates/docs and must never protect a real admin.
DISALLOWED_PASSWORDS = frozenset(
    {"changeme", "change-me", "change-me-to-a-random-secret-key", "password", "password123", "admin", "secret"}
)


def resolve_role(role_raw: str) -> str | None:
    """Return the canonical role string, or ``None`` when it is not allowed."""
    value = (role_raw or "").strip().lower()
    return value if value in VALID_ROLES else None


def validate_credentials(email: str, password: str) -> str | None:
    """Return an error message describing why the inputs are unusable, else ``None``."""
    if not email or "@" not in email:
        return "ADMIN_EMAIL must be a valid email address."
    if not password:
        return "ADMIN_PASSWORD is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters."
    if password.strip().lower() in DISALLOWED_PASSWORDS:
        return "ADMIN_PASSWORD is a well-known placeholder; choose a real password."
    return None


async def main() -> int:
    email = os.getenv("ADMIN_EMAIL", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    full_name = os.getenv("ADMIN_FULL_NAME", "CivicPulse Admin").strip() or "CivicPulse Admin"
    role_raw = os.getenv("ADMIN_ROLE", "admin")

    error = validate_credentials(email, password)
    if error:
        print(f"[create_admin] {error}", flush=True)
        return 2

    role_value = resolve_role(role_raw)
    if role_value is None:
        print(f"[create_admin] ADMIN_ROLE must be one of {VALID_ROLES} (got {role_raw!r}).", flush=True)
        return 2

    from sqlalchemy import select

    import src.models  # noqa: F401 — register every ORM model on Base.metadata
    from src.core.database import AsyncSessionLocal, init_db
    from src.core.security import hash_password_async
    from src.domains.users.models.user import User, UserRole

    # Creates tables in non-production environments (ENVIRONMENT=development),
    # matching seed_user.py; production deployments use Alembic beforehand.
    if not await init_db():
        print("[create_admin] init_db() failed — is the database reachable?", flush=True)
        return 1

    role = UserRole(role_value)
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        password_hash = await hash_password_async(password)
        if user is None:
            user = User(
                email=email,
                full_name=full_name,
                role=role,
                password_hash=password_hash,
                is_active=True,
            )
            session.add(user)
            action = "created"
        else:
            user.full_name = full_name
            user.password_hash = password_hash
            user.role = role
            user.is_active = True
            # An OAuth-bound account has no usable password (login is refused),
            # so clear the binding — otherwise the bootstrap password would be
            # silently ignored.
            user.oauth_provider = None
            user.oauth_sub = None
            action = "updated"
        await session.commit()
        print(f"[create_admin] {role.value} {email} {action} (id={user.id})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
