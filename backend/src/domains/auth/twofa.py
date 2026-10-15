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
    verify_password_for_login_async,
)
from src.domains.users.repositories.user_repository import UserRepository
from src.shared.errors import (
    InvalidCredentials,
    InvalidTwoFactorCode,
    TwoFactorAlreadyEnabled,
    TwoFactorNotEnabled,
    UserNotFound,
)

logger = logging.getLogger("civicpulse")

# 10 recovery codes, each in XXXX-XXXX-XXXX-XXXX format (16 hex chars = 64 bits)
_RECOVERY_CODE_COUNT = 10
_RECOVERY_CODE_BYTES = 8  # 64 bits of entropy per code

# scrypt parameters for recovery-code hashing. Deliberately modest: these run
# once per login attempt on a 6-digit input, but must still make an offline
# attack over a stolen DB costly. n=2**15/r=8/p=1 is ~32 MiB and ~50 ms.
_RECOVERY_SCRYPT_N = 2**15
_RECOVERY_SCRYPT_R = 8
_RECOVERY_SCRYPT_P = 1


def _generate_recovery_codes() -> list[str]:
    """Generate plain-text recovery codes. Returned to the user once at
    enable time; the caller must store *hashed* versions in the DB.

    Was ``secrets.token_hex(4)`` — 32 bits, 4 billion values — hashed with a
    bare SHA-256. An attacker holding the DB could exhaust the entire space in
    minutes on a GPU, so every recovery code was effectively known. 64 bits
    makes the same search ~2^32 times harder, and scrypt with a per-code salt
    removes the rainbow-table/vectorisation win that plain SHA-256 handed them.
    """
    codes = []
    for _ in range(_RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(_RECOVERY_CODE_BYTES)  # 16 hex chars
        codes.append("-".join(raw[i : i + 4] for i in range(0, len(raw), 4)))
    return codes


def _hash_recovery_code(code: str, salt: str | None = None) -> str:
    """Hash a normalised recovery code.

    Returns a versioned, self-describing string::

        scrypt$<salt_hex>$<hash_hex>

    Older rows hold a bare 64-char SHA-256 hex digest with no salt. Those are
    still *verified* by :func:`_verify_recovery_code` so existing users are not
    locked out, but nothing new is written in that format.
    """
    normalised = code.strip().upper()
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.scrypt(
        normalised.encode(),
        salt=salt_bytes,
        n=_RECOVERY_SCRYPT_N,
        r=_RECOVERY_SCRYPT_R,
        p=_RECOVERY_SCRYPT_P,
        dklen=32,
    )
    return f"scrypt${salt_bytes.hex()}${digest.hex()}"


def _verify_recovery_code(code: str, stored: str) -> bool:
    """Constant-time check of ``code`` against one stored entry.

    Handles both the salted scrypt format and the legacy unsalted SHA-256 form.
    A malformed stored value fails closed rather than raising.
    """
    normalised = code.strip().upper()
    if stored.startswith("scrypt$"):
        try:
            _, salt_hex, digest_hex = stored.split("$", 2)
            expected = _hash_recovery_code(normalised, salt=salt_hex)
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(expected, f"scrypt${salt_hex}${digest_hex}")
    # Legacy bare-hex SHA-256.
    if len(stored) == 64 and all(c in "0123456789abcdef" for c in stored):
        legacy = hashlib.sha256(normalised.encode()).hexdigest()
        return hmac.compare_digest(legacy, stored)
    return False


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
        if not user:
            raise InvalidCredentials()
        # Refuses OAuth-bound accounts and the legacy public sentinel before any
        # Argon2 work; a wrong password and an OAuth account look identical to
        # the caller.
        if not await verify_password_for_login_async(password, user.password_hash, oauth_provider=user.oauth_provider):
            raise InvalidCredentials()
        if not user.is_active:
            from src.shared.errors import UnauthorizedError

            raise UnauthorizedError(detail="Account is deactivated.")

        if user.two_factor_enabled:
            return create_2fa_challenge_token(user.id)

        from src.core.security import create_access_token, create_refresh_token
        from src.domains.auth.services.auth_service import clear_refresh_family_revocation, store_refresh_session

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        await clear_refresh_family_revocation(user.id)
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
            try:
                stored_codes: list[str] = json.loads(user.recovery_codes)
            except (TypeError, ValueError):
                raise InvalidTwoFactorCode()
            if not isinstance(stored_codes, list):
                raise InvalidTwoFactorCode()

            # Each stored entry carries its own salt, so the candidate must be
            # verified *against* the entry — hashing the input once and
            # comparing (the old approach) is impossible with per-code salts
            # and was the reason the previous code had to use bare SHA-256.
            # Every entry is checked rather than stopping at the first match,
            # so the timing profile does not reveal which slot matched; the
            # loop therefore cannot mutate the list while iterating.
            matched_index = -1
            for i, stored in enumerate(stored_codes):
                if not isinstance(stored, str):
                    continue
                if _verify_recovery_code(code_clean, stored):
                    matched_index = i
            if matched_index < 0:
                raise InvalidTwoFactorCode()

            # Remove the used recovery code.
            stored_codes.pop(matched_index)
            user.recovery_codes = json.dumps(stored_codes) if stored_codes else None
            await self.db.commit()

        from src.core.security import create_access_token, create_refresh_token
        from src.domains.auth.services.auth_service import clear_refresh_family_revocation, store_refresh_session

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        await clear_refresh_family_revocation(user.id)
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
