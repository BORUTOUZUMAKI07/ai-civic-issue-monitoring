"""auth hardening: totp encryption support fields, email verification, replay counter

Revision ID: 011_auth_hardening_email_gdpr
Revises: 010_enforce_model_not_null_columns
Create Date: 2026-11-19

Adds:
- users.totp_last_counter (replay protection for TOTP time-step codes)
- users.email_verified (default true for existing accounts to avoid lockout)
- users.email_verified_at

Also encrypts any existing plaintext TOTP secrets at rest (AES-256-GCM) when a
key is available from ENCRYPTION_KEY/SECRET_KEY. If encryption cannot be
performed, plaintext secrets are left as-is and the application can migrate
them lazily on read/write.
"""

from __future__ import annotations

import base64
import hashlib
import os

import sqlalchemy as sa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from alembic import op

revision = "011_auth_hardening_email_gdpr"
down_revision = "010"
branch_labels = None
depends_on = None


def _derived_key() -> bytes | None:
    try:
        from src.core.config import settings

        material = settings.ENCRYPTION_KEY or settings.SECRET_KEY
        if not material:
            return None
        return hashlib.sha256(material.encode()).digest()
    except Exception:
        return None


def _looks_encrypted(value: str | None) -> bool:
    if not value:
        return False
    if all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=" for c in value.upper().replace(" ", "")):
        return False
    try:
        raw = base64.b64decode(value.encode(), validate=True)
    except Exception:
        return False
    return len(raw) >= 28


def _encrypt(key: bytes, plain_text: str) -> str:
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plain_text.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("totp_last_counter", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("true")))
        batch_op.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))

    # Best-effort in-place encryption of legacy plaintext TOTP secrets.
    key = _derived_key()
    if key:
        bind = op.get_bind()
        rows = bind.execute(sa.text("SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL")).fetchall()
        for row in rows:
            secret = row.totp_secret
            if not secret or _looks_encrypted(secret):
                continue
            try:
                enc = _encrypt(key, secret)
            except Exception:
                continue
            bind.execute(
                sa.text("UPDATE users SET totp_secret = :enc WHERE id = :id"),
                {"enc": enc, "id": row.id},
            )

    # Drop server_default to match application-level default behavior.
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("email_verified", server_default=None)


def downgrade() -> None:
    # Schema is symmetric: every column added above is removed. TOTP ciphertext
    # is intentionally NOT decrypted — the key may have rotated since upgrade,
    # and a downgrade must never write plaintext secrets back into the table.
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("email_verified")
        batch_op.drop_column("totp_last_counter")
