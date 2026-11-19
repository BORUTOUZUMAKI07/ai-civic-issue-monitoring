from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone

import pyotp
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import (
    create_2fa_challenge_token,
    decrypt_secret,
    encrypt_secret,
    looks_like_encrypted_secret,
    verify_password_for_login_async,
)
from src.domains.users.repositories.user_repository import UserRepository
from src.shared.errors import (
    EmailNotVerified,
    InvalidCredentials,
    InvalidTwoFactorCode,
    TwoFactorAlreadyEnabled,
    TwoFactorNotEnabled,
    UserNotFound,
)

logger = logging.getLogger("civicpulse")

_RECOVERY_CODE_COUNT = 10
_RECOVERY_CODE_BYTES = 8

_RECOVERY_SCRYPT_N = 2**15
_RECOVERY_SCRYPT_R = 8
_RECOVERY_SCRYPT_P = 1


def _generate_recovery_codes() -> list[str]:
    codes = []
    for _ in range(_RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(_RECOVERY_CODE_BYTES)
        codes.append("-".join(raw[i : i + 4] for i in range(0, len(raw), 4)))
    return codes


def _hash_recovery_code(code: str, salt: str | None = None) -> str:
    normalised = code.strip().upper()
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.scrypt(
        normalised.encode(),
        salt=salt_bytes,
        n=_RECOVERY_SCRYPT_N,
        r=_RECOVERY_SCRYPT_R,
        p=_RECOVERY_SCRYPT_P,
        dklen=32,
        maxmem=2**30,
    )
    return f"scrypt${salt_bytes.hex()}${digest.hex()}"


def _verify_recovery_code(code: str, stored: str) -> bool:
    normalised = code.strip().upper()
    if stored.startswith("scrypt$"):
        try:
            _, salt_hex, digest_hex = stored.split("$", 2)
            expected = _hash_recovery_code(normalised, salt=salt_hex)
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(expected, stored)
    if len(stored) == 64 and all(c in "0123456789abcdef" for c in stored):
        legacy = hashlib.sha256(normalised.encode()).hexdigest()
        return hmac.compare_digest(legacy, stored)
    return False


def _store_recovery_codes(codes: list[str]) -> str:
    return json.dumps([_hash_recovery_code(c) for c in codes])


def _read_totp_secret(stored: str | None) -> str | None:
    if not stored:
        return None
    # Backward compatibility: existing plaintext base32 secrets may remain until
    # first successful verification/write, or if migration could not encrypt.
    if looks_like_encrypted_secret(stored):
        try:
            return decrypt_secret(stored)
        except Exception:
            return None
    return stored


def _store_totp_secret(secret: str) -> str:
    return encrypt_secret(secret)


def _matching_totp_counter(totp: pyotp.TOTP, code: str) -> int | None:
    """Return the matched TOTP time-step counter, or None if invalid.

    Mirrors Nexus replay protection: the accepted counter is recorded so the same
    (or an earlier) step cannot be redeemed again.
    """
    now = datetime.now(timezone.utc)
    interval = int(getattr(totp, "interval", 30) or 30)
    window = max(int(getattr(settings, "TOTP_VALID_WINDOW", 1) or 1), 0)
    for offset in range(-window, window + 1):
        candidate_time = datetime.fromtimestamp(now.timestamp() + offset * interval, tz=timezone.utc)
        try:
            if hmac.compare_digest(str(totp.at(candidate_time)), str(code)):
                return int(totp.timecode(candidate_time))
        except Exception:
            continue
    return None


def _accept_totp_counter(user, counter: int) -> bool:
    last = getattr(user, "totp_last_counter", None)
    if isinstance(last, int) and counter <= last:
        return False
    user.totp_last_counter = counter
    return True


class TwoFactorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def enable(self, user_id: int) -> tuple[str, str]:
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        if user.two_factor_enabled:
            raise TwoFactorAlreadyEnabled()

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name="CivicPulse")

        # Store encrypted at rest; keep a pending (not-yet-enabled) secret.
        user.totp_secret = _store_totp_secret(secret)
        user.totp_last_counter = None
        await self.db.commit()

        return secret, provisioning_uri

    async def confirm(self, user_id: int, code: str) -> list[str]:
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        if user.two_factor_enabled:
            raise TwoFactorAlreadyEnabled()
        secret = _read_totp_secret(user.totp_secret)
        if not secret:
            raise TwoFactorNotEnabled()

        totp = pyotp.TOTP(secret)
        counter = _matching_totp_counter(totp, code.strip())
        if counter is None or not _accept_totp_counter(user, counter):
            raise InvalidTwoFactorCode()

        recovery_codes = _generate_recovery_codes()
        user.two_factor_enabled = True
        # Ensure secret is stored encrypted going forward (migrates legacy plaintext).
        user.totp_secret = _store_totp_secret(secret)
        user.recovery_codes = _store_recovery_codes(recovery_codes)
        await self.db.commit()

        return recovery_codes

    async def disable(self, user_id: int, code: str) -> None:
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        if not user.two_factor_enabled:
            raise TwoFactorNotEnabled()
        secret = _read_totp_secret(user.totp_secret)
        if not secret:
            raise TwoFactorNotEnabled()

        totp = pyotp.TOTP(secret)
        counter = _matching_totp_counter(totp, code.strip())
        if counter is None or not _accept_totp_counter(user, counter):
            raise InvalidTwoFactorCode()

        user.two_factor_enabled = False
        user.totp_secret = None
        user.totp_last_counter = None
        user.recovery_codes = None
        await self.db.commit()

    async def verify_or_challenge(self, email: str, password: str) -> str | tuple[str, str]:
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise InvalidCredentials()
        if not await verify_password_for_login_async(password, user.password_hash, oauth_provider=user.oauth_provider):
            raise InvalidCredentials()
        if not user.is_active:
            from src.shared.errors import UnauthorizedError

            raise UnauthorizedError(detail="Account is deactivated.")
        if getattr(settings, "EMAIL_VERIFICATION_REQUIRED", False) and not getattr(user, "email_verified", True):
            raise EmailNotVerified()

        if user.two_factor_enabled:
            return create_2fa_challenge_token(user.id)

        from src.core.security import create_access_token, create_refresh_token
        from src.domains.auth.services.auth_service import (
            clear_refresh_family_revocation,
            clear_refresh_revocation,
            store_refresh_session,
        )

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        await clear_refresh_family_revocation(user.id)
        await clear_refresh_revocation(user.id)
        await store_refresh_session(refresh_token)
        return access_token, refresh_token

    async def verify_challenge(self, user_id: int, code: str) -> tuple[str, str]:
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        if not user.two_factor_enabled:
            raise TwoFactorNotEnabled()

        code_clean = code.strip().upper()

        totp_ok = False
        secret = _read_totp_secret(user.totp_secret)
        if secret:
            totp = pyotp.TOTP(secret)
            counter = _matching_totp_counter(totp, code_clean)
            if counter is not None and _accept_totp_counter(user, counter):
                # Migrate legacy plaintext secret to encrypted form on successful use.
                if user.totp_secret and not looks_like_encrypted_secret(user.totp_secret):
                    user.totp_secret = _store_totp_secret(secret)
                totp_ok = True

        if not totp_ok:
            if not user.recovery_codes:
                raise InvalidTwoFactorCode()
            try:
                stored_codes: list[str] = json.loads(user.recovery_codes)
            except (TypeError, ValueError):
                raise InvalidTwoFactorCode()
            if not isinstance(stored_codes, list):
                raise InvalidTwoFactorCode()

            matched_index = -1
            for i, stored in enumerate(stored_codes):
                if not isinstance(stored, str):
                    continue
                if _verify_recovery_code(code_clean, stored):
                    matched_index = i
                    break
            if matched_index < 0:
                raise InvalidTwoFactorCode()

            stored_codes.pop(matched_index)
            user.recovery_codes = json.dumps(stored_codes) if stored_codes else None
            await self.db.commit()

        from src.core.security import create_access_token, create_refresh_token
        from src.domains.auth.services.auth_service import (
            clear_refresh_family_revocation,
            clear_refresh_revocation,
            store_refresh_session,
        )

        if totp_ok:
            await self.db.commit()

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        await clear_refresh_family_revocation(user.id)
        await clear_refresh_revocation(user.id)
        await store_refresh_session(refresh_token)
        return access_token, refresh_token

    async def regenerate_recovery_codes(self, user_id: int, code: str) -> list[str]:
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        if not user.two_factor_enabled:
            raise TwoFactorNotEnabled()
        secret = _read_totp_secret(user.totp_secret)
        if not secret:
            raise TwoFactorNotEnabled()

        totp = pyotp.TOTP(secret)
        counter = _matching_totp_counter(totp, code.strip())
        if counter is None or not _accept_totp_counter(user, counter):
            raise InvalidTwoFactorCode()

        recovery_codes = _generate_recovery_codes()
        if user.totp_secret and not looks_like_encrypted_secret(user.totp_secret):
            user.totp_secret = _store_totp_secret(secret)
        user.recovery_codes = _store_recovery_codes(recovery_codes)
        await self.db.commit()

        return recovery_codes
