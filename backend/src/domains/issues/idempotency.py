"""Idempotency-key handling for issue creation.

A ``POST /issues/upload`` carries an optional ``Idempotency-Key`` header,
scoped to the authenticated user. The row lifecycle is::

    in_progress  ->  succeeded
                 ->  failed

* replayed key in ``succeeded`` → the stored response is returned verbatim,
  tagged ``Idempotency-Replayed: true``;
* key in ``in_progress`` → 409 while the original request is still running;
* key in ``failed`` → retryable: the previous attempt raised before completing,
  so a new attempt may proceed;
* a key reused with a *different* request body → 400. The key means "the same
  logical request", not "any request from this client".

Boundary worth stating plainly: the key guarantees *no duplicate issue row on
the common client retry* (the request that never got a response). It does not
wrap the whole create-and-assign flow in one transaction, so a failure that
happens after the issue row commits — the engineer-assignment step — still
leaves one issue behind, and a retry then makes a second. Making that fully
atomic is a larger change to ``IssueService`` and is out of scope here.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.issues.models.idempotency import IdempotencyKey, IdempotencyStatus

MAX_KEY_LENGTH = 128


def hash_request(
    user_id: int,
    latitude: float,
    longitude: float,
    description: str,
    force_submit: bool,
    filename: str,
    content: bytes,
) -> str:
    """Stable SHA-256 fingerprint of the logical upload request.

    Includes the image bytes' own digest so reusing a key with a different
    photo is caught, not just a different description.
    """
    payload = "\n".join(
        [
            str(user_id),
            repr(latitude),
            repr(longitude),
            description,
            str(force_submit),
            filename,
            hashlib.sha256(content).hexdigest(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_record(db: AsyncSession, user_id: int, key: str) -> IdempotencyKey | None:
    result = await db.execute(
        select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
    )
    return result.scalar_one_or_none()


async def start_in_progress(db: AsyncSession, user_id: int, key: str, request_hash: str) -> IdempotencyKey | None:
    """Insert an in-progress record.

    Returns the new record, or ``None`` when the key already exists — a
    concurrent identical request won the race on the unique constraint.
    """
    now = datetime.now(timezone.utc)
    record = IdempotencyKey(
        key=key,
        user_id=user_id,
        request_sha256=request_hash,
        status=IdempotencyStatus.in_progress,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    try:
        await db.commit()
        await db.refresh(record)
        return record
    except IntegrityError:
        await db.rollback()
        return None


async def mark_succeeded(
    db: AsyncSession, record: IdempotencyKey, response_status: int, response_body: dict[str, Any]
) -> None:
    record.status = IdempotencyStatus.succeeded
    record.response_status = response_status
    record.response_body = json.dumps(response_body)
    record.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def mark_failed(db: AsyncSession, record: IdempotencyKey) -> None:
    record.status = IdempotencyStatus.failed
    record.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def reclaim_failed(db: AsyncSession, record: IdempotencyKey) -> bool:
    """Atomically move a ``failed`` record back to ``in_progress``.

    Returns ``True`` only for the retry that actually flipped the row, so two
    concurrent retries of the same key cannot both proceed.
    """
    result = await db.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.id == record.id, IdempotencyKey.status == IdempotencyStatus.failed)
        .values(status=IdempotencyStatus.in_progress, updated_at=datetime.now(timezone.utc))
    )
    await db.commit()
    # `db.execute` on an UPDATE returns a CursorResult, whose `rowcount` is the
    # number of matched rows; the cast restores that attribute lost to the
    # generic `Result` return type.
    return bool(cast(Any, result).rowcount == 1)
