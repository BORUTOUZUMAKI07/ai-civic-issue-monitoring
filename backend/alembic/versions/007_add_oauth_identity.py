"""Bind OAuth accounts to a provider identity instead of a shared sentinel

Revision ID: 007
Revises: 006
Create Date: 2026-10-07

Adds ``oauth_provider`` / ``oauth_sub`` so an account's identity is established
by the provider's subject id (the only authoritative link) rather than by an
email address.  When ``oauth_provider`` is set the account has no usable
password and password login is refused outright.

It also sweeps the legacy damage: OAuth accounts created before this revision
stored ``hash("!")`` as their password, and because Argon2 will happily hash and
verify the literal ``"!"``, every such account's password was public knowledge.
Any row whose hash still verifies the literal is reset to a random value.

The sweep is deliberately best-effort: it needs ``passlib`` + ``argon2-cffi``,
and a failure to import them must not abort the migration or leave the schema
half-applied.  The code-level guard in ``verify_password_for_login`` closes the
hole regardless, so the sweep is remediation of stored state, not the fix.
"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("civicpulse")

_LEGACY_SENTINELS = ("!",)


def upgrade() -> None:
    op.add_column("users", sa.Column("oauth_provider", sa.String(), nullable=True))
    op.add_column("users", sa.Column("oauth_sub", sa.String(), nullable=True))
    op.create_index("ix_users_oauth_provider", "users", ["oauth_provider"], unique=False)

    _reset_legacy_sentinel_hashes()


def downgrade() -> None:
    op.drop_index("ix_users_oauth_provider", table_name="users")
    op.drop_column("users", "oauth_sub")
    op.drop_column("users", "oauth_provider")


def _reset_legacy_sentinel_hashes() -> None:
    """Replace every ``hash("!")`` with a fresh random hash.

    Runs outside the transaction's failure path on purpose: if the hashing
    stack is unavailable we log loudly and let the columns stand.
    """
    try:
        import secrets

        from passlib.context import CryptContext
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "007: could not import hashing stack (%s); legacy sentinel hashes left in place. "
            "Password login already refuses them at runtime.",
            exc,
        )
        return

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, password_hash FROM users WHERE oauth_provider IS NULL")
    ).fetchall()
    if not rows:
        return

    pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
    resets = []
    for user_id, password_hash in rows:
        if not password_hash:
            continue
        try:
            if pwd_context.verify("!", password_hash):
                resets.append((pwd_context.hash(secrets.token_urlsafe(32)), user_id))
        except Exception:
            # An unparseable hash is not ours to judge; skip it rather than
            # aborting the migration over one bad row.
            continue

    if not resets:
        return

    for new_hash, user_id in resets:
        bind.execute(
            sa.text("UPDATE users SET password_hash = :h WHERE id = :i"),
            {"h": new_hash, "i": user_id},
        )
    logger.warning("007: reset %d OAuth accounts that stored a public sentinel hash", len(resets))
