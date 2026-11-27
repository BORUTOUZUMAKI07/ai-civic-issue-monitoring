from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from src.core.config import settings
from src.core.email import send_email
from src.core.security import _standard_claims, hash_password_async
from src.core.security_store import consume_one_time, mark_revoked
from src.domains.users.repositories.user_repository import UserRepository
from src.shared.errors import PasswordResetTokenInvalid

logger = logging.getLogger("civicpulse")

_RESET_JTI_PREFIX = "pwreset:used:"


def create_password_reset_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    return str(
        jwt.encode(
            {
                "sub": str(user_id),
                "type": "password_reset",
                "jti": uuid4().hex,
                "exp": expire,
                **_standard_claims(),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
    )


def decode_password_reset_token(token: str) -> tuple[int, str | None]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
    except Exception:
        raise PasswordResetTokenInvalid()
    if payload.get("type") != "password_reset":
        raise PasswordResetTokenInvalid()
    try:
        return int(payload["sub"]), payload.get("jti")
    except (KeyError, TypeError, ValueError):
        raise PasswordResetTokenInvalid()


def build_reset_link(reset_token: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/reset-password?token={reset_token}"


async def send_password_reset_email(db, email: str) -> bool:
    user = await UserRepository(db).get_by_email(email)
    if user is None:
        logger.info("password_reset: request for an unregistered address ignored")
        return True

    token = create_password_reset_token(user.id)
    link = build_reset_link(token)
    subject = settings.PASSWORD_RESET_EMAIL_SUBJECT
    body = (
        "Hello,\n\n"
        "We received a request to reset your CivicPulse password.\n"
        "Click the link below to choose a new password (valid for "
        f"{settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes):\n\n"
        f"{link}\n\n"
        "If you did not request this, you can ignore this email.\n\n"
        "- CivicPulse"
    )
    sent = send_email(subject, email, body)
    if not sent:
        logger.error("password_reset: failed to send a reset email to a registered address")
        return True
    return True


async def reset_password(db, token: str, new_password: str) -> None:
    user_id, jti = decode_password_reset_token(token)

    if jti:
        already_used = await _consume_reset_jti(jti)
        if already_used:
            raise PasswordResetTokenInvalid()

    repo = UserRepository(db)
    user = await repo.get(user_id)
    if user is None:
        raise PasswordResetTokenInvalid()

    user.password_hash = await hash_password_async(new_password)
    await db.commit()
    await db.refresh(user)

    # Both operations are security boundaries. If either fails, the password
    # change must not be reported as successful: the reset token could be
    # replayed or the old sessions could remain valid.
    await revoke_all_refresh_sessions(user.id)
    from src.domains.auth.services.auth_service import clear_user_revocation

    await clear_user_revocation(user.id)


async def _consume_reset_jti(jti: str) -> bool:
    key = f"{_RESET_JTI_PREFIX}{jti}"
    ttl = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES * 60
    return await consume_one_time(key, ttl)


async def revoke_all_refresh_sessions(user_id: int) -> None:
    ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await mark_revoked(f"refresh:revoked:{user_id}", ttl)
