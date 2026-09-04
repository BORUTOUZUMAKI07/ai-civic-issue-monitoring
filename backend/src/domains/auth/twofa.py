from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets

import pyotp
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import (
    create_2fa_challenge_token,
    verify_password_async,
)
from src.errors import (
    InvalidCredentials,
    InvalidTwoFactorCode,
    TwoFactorAlreadyEnabled,
    TwoFactorNotEnabled,
    UserNotFound,
)
from src.repositories.user_repository import UserRepository

logger = logging.getLogger("civicpulse")

# 10 recovery codes, each in XXXX-XXXX format (8 hex chars)
_RECOVERY_CODE_COUNT = 10


def _generate_recovery_codes() -> list[str]:
    """Generate plain-text recovery codes. Returned to the user once at
    enable time; the caller must store *hashed* versions in the DB."""
    codes = []
    for _ in range(_RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(4)  # 8 hex chars
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def _hash_recovery_code(code: str) -> str:
    """SHA-256 hash of the normalised (upper, stripped) code."""
    normalised = code.strip().upper()
    return hashlib.sha256(normalised.encode()).hexdigest()


def _store_recovery_codes(codes: list[str]) -> str:
    """Hash the plain-text codes and return a JSON array string for DB storage."""
    return json.dumps([_hash_recovery_code(c) for c in codes])


class TwoFactorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    # ---- Enable flow (step 1: generate secret, step 2: confirm) ----

    async def enable(self, user_id: int) -> tuple[str, str]:
        """Generate a TOTP secret and provisioning URI. Does NOT enable 2FA
        yet — the user must confirm with a valid code first.

        Returns (secret, provisioning_uri).
        """
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        if user.two_factor_enabled:
            raise TwoFactorAlreadyEnabled()

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name="CivicPulse")

        # Persist the secret so the confirm step can verify against it.
        user.totp_secret = secret
        await self.db.commit()

        return secret, provisioning_uri

    async def confirm(self, user_id: int, code: str) -> list[str]:
        """Verify the TOTP code against the pending secret and, if valid,
        activate 2FA. Returns a list of plain-text recovery codes (shown
        once to the user)."""
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        if user.two_factor_enabled:
            raise TwoFactorAlreadyEnabled()
        if not user.totp_secret:
            raise TwoFactorNotEnabled()

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(code, valid_window=1):
            raise InvalidTwoFactorCode()

        # Activate and store hashed recovery codes.
        recovery_codes = _generate_recovery_codes()
        user.two_factor_enabled = True
        user.recovery_codes = _store_recovery_codes(recovery_codes)
        await self.db.commit()

        return recovery_codes

    async def disable(self, user_id: int, code: str) -> None:
        """Disable 2FA after verifying a valid TOTP code."""
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        if not user.two_factor_enabled:
            raise TwoFactorNotEnabled()

        if not user.totp_secret:
            raise TwoFactorNotEnabled()

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(code, valid_window=1):
            raise InvalidTwoFactorCode()

        user.two_factor_enabled = False
        user.totp_secret = None
        user.recovery_codes = None
        await self.db.commit()

    # ---- Login flow ----

    async def verify_or_challenge(self, email: str, password: str) -> str | tuple[str, str]:
        """Login step 1.

        - If 2FA is **not** enabled, returns ``(access_token, refresh_token)``.
        - If 2FA **is** enabled, returns the challenge token string (the
          caller must return this to the frontend so the user can complete
          the second step).
        """
        user = await self.user_repo.get_by_email(email)
        if not user or not await verify_password_async(password, user.password_hash):
            raise InvalidCredentials()
        if not user.is_active:
            from src.errors import UnauthorizedError

            raise UnauthorizedError(detail="Account is deactivated.")

        if user.two_factor_enabled:
            return create_2fa_challenge_token(user.id)

        from src.core.security import create_access_token, create_refresh_token
        from src.domains.auth.service import store_refresh_session

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        await store_refresh_session(refresh_token)
        return access_token, refresh_token

    async def verify_challenge(self, user_id: int, code: str) -> tuple[str, str]:
        """Login step 2 — verify the TOTP code (or recovery code) and issue
        real tokens."""
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        if not user.two_factor_enabled:
            raise TwoFactorNotEnabled()

        code_clean = code.strip().upper()

        # Try TOTP first.
        totp_ok = False
        if user.totp_secret:
            totp = pyotp.TOTP(user.totp_secret)
            totp_ok = totp.verify(code_clean, valid_window=1)

        if totp_ok:
            pass  # proceed to issue tokens
        else:
            # Try recovery code.
            if not user.recovery_codes:
                raise InvalidTwoFactorCode()
            stored_hashes: list[str] = json.loads(user.recovery_codes)
            provided_hash = _hash_recovery_code(code_clean)
            # Constant-time comparison of each stored hash.
            matched = False
            for i, h in enumerate(stored_hashes):
                if hmac.compare_digest(h, provided_hash):
                    matched = True
                    stored_hashes.pop(i)
                    break
            if not matched:
                raise InvalidTwoFactorCode()
            # Remove the used recovery code.
            user.recovery_codes = json.dumps(stored_hashes) if stored_hashes else None
            await self.db.commit()

        from src.core.security import create_access_token, create_refresh_token
        from src.domains.auth.service import store_refresh_session

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        await store_refresh_session(refresh_token)
        return access_token, refresh_token

    async def regenerate_recovery_codes(self, user_id: int, code: str) -> list[str]:
        """Issue new recovery codes (invalidates old ones). Requires a valid
        TOTP code."""
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        if not user.two_factor_enabled:
            raise TwoFactorNotEnabled()
        if not user.totp_secret:
            raise TwoFactorNotEnabled()

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(code, valid_window=1):
            raise InvalidTwoFactorCode()

        recovery_codes = _generate_recovery_codes()
        user.recovery_codes = _store_recovery_codes(recovery_codes)
        await self.db.commit()

        return recovery_codes
