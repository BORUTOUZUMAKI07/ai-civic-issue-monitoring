"""Password reset: token issuance, email sending, and password update.

The reset token is a short-lived signed JWT (``type=password_reset``). The
link embedded in the email points at the frontend, which then calls the backend
reset endpoint with the token. This keeps credentials off the wire.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from jose import jwt

from src.core.config import settings
from src.core.email import send_email
from src.core.security import hash_password
from src.errors import PasswordResetEmailNotSent, PasswordResetTokenInvalid
from src.repositories.user_repository import UserRepository

logger = logging.getLogger("civicpulse")


def create_password_reset_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "password_reset",
            "exp": expire,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_password_reset_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except Exception:
        raise PasswordResetTokenInvalid()
    if payload.get("type") != "password_reset":
        raise PasswordResetTokenInvalid()
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise PasswordResetTokenInvalid()


def build_reset_link(reset_token: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/reset-password?token={reset_token}"


async def send_password_reset_email(db, email: str) -> bool:
    """Send a reset link if the user exists. Always returns soft success to
    avoid leaking whether an address is registered."""
    user = await UserRepository(db).get_by_email(email)
    if user is None:
        # Do not reveal account existence; still pretend success.
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
        "— CivicPulse"
    )
    sent = send_email(subject, email, body)
    if not sent:
        raise PasswordResetEmailNotSent()
    return True


async def reset_password(db, token: str, new_password: str) -> None:
    user_id = decode_password_reset_token(token)
    repo = UserRepository(db)
    user = await repo.get(user_id)
    if user is None:
        raise PasswordResetTokenInvalid()
    user.password_hash = hash_password(new_password)
    await db.commit()
    await db.refresh(user)
