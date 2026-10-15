"""Password reset: token issuance, email sending, and password update.

The reset token is a short-lived signed JWT (``type=password_reset``). The
link embedded in the email points at the frontend, which then calls the backend
reset endpoint with the token. This keeps credentials off the wire.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import jwt

from src.core.config import settings
from src.core.email import send_email
from src.core.redis import redis_client
from src.core.security import hash_password_async
from src.repositories.user_repository import UserRepository
from src.shared.errors import PasswordResetTokenInvalid

logger = logging.getLogger("civicpulse")

# Single-use marker for a consumed reset token. A signed JWT is bearer-proof
# but stateless, so without this the emailed link stays valid for its whole
# TTL: anyone who intercepts it (or who simply clicks twice) can replay it
# for the full window and re-set a password they already set once.
_RESET_JTI_PREFIX = "pwreset:used:"


def create_password_reset_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    # `python-jose` is untyped, so `jwt.encode` returns `Any`; wrap it so the
    # `-> str` contract is actually enforced at the boundary.
    return str(
        jwt.encode(
            {
                "sub": str(user_id),
                "type": "password_reset",
                "jti": uuid4().hex,
                "exp": expire,
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
    )


def decode_password_reset_token(token: str) -> tuple[int, str | None]:
    """Validate the token and return ``(user_id, jti)``.

    Raises ``PasswordResetTokenInvalid`` on any mismatch. The ``jti`` is
    returned so the caller can mark it consumed; it may be ``None`` for tokens
    minted before ``jti`` existed, which are still checked for type/expiry but
    cannot be single-used.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
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
    """Send a reset link if the user exists. **Always** returns soft success.

    The response must not depend on anything about the account — existence,
    or whether the mail server cooperated. An earlier version returned
    ``True`` for an unknown address but let ``PasswordResetEmailNotSent``
    propagate for a known one, so a single request distinguished registered
    from unregistered addresses (and, with a flaky SMTP, leaked which
    addresses had a mailbox that accepted mail). Mail failures are now logged
    and swallowed exactly like unknown addresses.
    """
    user = await UserRepository(db).get_by_email(email)
    if user is None:
        # Do not reveal account existence; still pretend success.
        logger.info("password_reset: request for an unregistered address (ignored)")
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
        # Swallowed on purpose — see the docstring. The operator still learns
        # about it from the log, which is the only channel that does not
        # reach the caller.
        logger.error("password_reset: failed to send a reset email to a registered address")
        return True
    return True


async def reset_password(db, token: str, new_password: str) -> None:
    user_id, jti = decode_password_reset_token(token)

    # Consume the token *before* doing any work: a token that has already been
    # used must be rejected even if the password update below then fails, or
    # the failure path hands the attacker another attempt with the same link.
    if jti:
        already_used = await _consume_reset_jti(jti)
        if already_used:
            raise PasswordResetTokenInvalid()

    repo = UserRepository(db)
    user = await repo.get(user_id)
    if user is None:
        raise PasswordResetTokenInvalid()

    # Hashing Argon2 is ~100-200ms of CPU. The synchronous ``hash_password``
    # ran it directly on the event loop, so a handful of concurrent resets
    # stalled every other request — a trivial denial of service on an
    # unauthenticated endpoint. Offload it like every other call site does.
    user.password_hash = await hash_password_async(new_password)
    await db.commit()
    await db.refresh(user)

    # A password change must end every existing session: the whole point of a
    # reset is usually that the old password (and whatever sessions it minted)
    # are no longer trusted. Every refresh token for this user is revoked, so
    # the next refresh attempt fails and the browser is signed out.
    await revoke_all_refresh_sessions(user.id)


async def _consume_reset_jti(jti: str) -> bool:
    """Mark ``jti`` as used. Returns True if it was already used.

    Redis may be unavailable (it is best-effort everywhere else in this
    module's stack), in which case the token is *not* consumed and we fall
    back to time-boxed single use — strictly better than raising and leaving
    the user unable to reset at all.
    """
    key = f"{_RESET_JTI_PREFIX}{jti}"
    ttl = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES * 60
    try:
        # SET NX — the first caller wins; a second sees the key present.
        was_new = await redis_client.set(key, "1", ex=ttl, nx=True)
        return not bool(was_new)
    except Exception as exc:
        logger.warning("password_reset: could not persist token consumption (%s)", exc)
        return False


async def revoke_all_refresh_sessions(user_id: int) -> None:
    """Best-effort global sign-out for ``user_id``.

    Mirrors the family-revocation flag used by refresh-rotation reuse
    detection, so the two mechanisms share one code path and one TTL rather
    than drifting apart.
    """
    try:
        ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
        await redis_client.setex(f"refresh:revoked:{user_id}", ttl, "1")
    except Exception as exc:
        logger.warning("password_reset: could not revoke sessions for user %s (%s)", user_id, exc)
