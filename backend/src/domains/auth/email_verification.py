from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import redis as redis_module
from src.core.config import settings
from src.core.email import send_email
from src.domains.users.repositories.user_repository import UserRepository
from src.shared.errors import EmailVerificationTokenInvalid

logger = logging.getLogger("civicpulse")

_VERIFY_JTI_PREFIX = "emailverify:used:"


def create_email_verification_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES)
    return str(
        jwt.encode(
            {
                "sub": str(user_id),
                "type": "email_verify",
                "jti": uuid4().hex,
                "exp": expire,
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
    )


def decode_email_verification_token(token: str) -> tuple[int, str | None]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except Exception:
        raise EmailVerificationTokenInvalid()
    if payload.get("type") != "email_verify":
        raise EmailVerificationTokenInvalid()
    try:
        return int(payload["sub"]), payload.get("jti")
    except (KeyError, TypeError, ValueError):
        raise EmailVerificationTokenInvalid()


def build_verify_link(token: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/verify-email?token={token}"


async def send_verification_email(db: AsyncSession, user: Any) -> bool:
    if getattr(user, "email_verified", True):
        return True
    token = create_email_verification_token(user.id)
    link = build_verify_link(token)
    subject = settings.EMAIL_VERIFY_EMAIL_SUBJECT
    body = (
        "Hello,\n\n"
        "Please verify your CivicPulse account by clicking the link below (valid for "
        f"{settings.EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES} minutes):\n\n"
        f"{link}\n\n"
        "If you did not create this account, you can ignore this email.\n\n"
        "- CivicPulse"
    )
    sent = send_email(subject, user.email, body)
    if not sent:
        logger.error("email_verify: failed to send verification email")
        return False
    return True


async def verify_email_token(db: AsyncSession, token: str) -> Any:
    user_id, jti = decode_email_verification_token(token)
    if jti and await _consume_verify_jti(jti):
        raise EmailVerificationTokenInvalid()

    repo = UserRepository(db)
    user = await repo.get(user_id)
    if user is None:
        raise EmailVerificationTokenInvalid()

    if not getattr(user, "email_verified", True):
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(user)
    return user


async def _consume_verify_jti(jti: str) -> bool:
    key = f"{_VERIFY_JTI_PREFIX}{jti}"
    ttl = settings.EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES * 60
    try:
        was_new = await redis_module.redis_client.set(key, "1", ex=ttl, nx=True)
        return not bool(was_new)
    except Exception as exc:
        logger.warning("email_verify: could not persist token consumption (%s)", exc)
        return False
