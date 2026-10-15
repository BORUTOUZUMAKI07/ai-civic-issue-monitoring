"""Idempotent-upload contract tests.

These exercise the three fast paths of ``_idempotent_upload`` — replay, key
reuse with a different body, and in-flight conflict — without ever running the
vision/agent pipeline. Each path returns before ``_execute_upload`` is reached,
so the tests need no real image decoding, no ML model and no embeddings; the
"image" is opaque bytes and is only ever fingerprinted.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.core.database import AsyncSessionLocal
from src.domains.issues.idempotency import hash_request
from src.domains.issues.models.idempotency import IdempotencyKey, IdempotencyStatus

UPLOAD_URL = "/api/v1/issues/upload"

USER_ID = 1
FILENAME = "pothole.png"
# Never decoded on these paths — only hashed — so the bytes are arbitrary.
CONTENT = b"\x89PNG\r\n\x1a\nnot-a-real-image"
LAT = 22.3072
LON = 73.1812


def _stored_body() -> dict:
    return {
        "id": 4242,
        "issue_type": "pothole",
        "confidence": 0.9,
        "severity": 3,
        "status": "reported",
        "latitude": LAT,
        "longitude": LON,
        "description": "stored description",
        "image_url": "/uploads/issues/existing.png",
        "review_required": False,
        "ward_id": 1,
        "reporter_id": USER_ID,
        "created_at": "2026-01-01T00:00:00+00:00",
        "assigned_to": None,
        "engineer_name": None,
        "model_used": "vision",
        "probabilities": {"pothole": 0.9},
    }


async def _insert_record(
    *,
    key: str,
    status: IdempotencyStatus,
    request_hash: str,
    body: dict | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        session.add(
            IdempotencyKey(
                key=key,
                user_id=USER_ID,
                request_sha256=request_hash,
                status=status,
                response_status=200 if body is not None else None,
                response_body=json.dumps(body) if body is not None else None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


async def _post(client, auth_headers, *, key: str, description: str = "stored description"):
    return await client.post(
        UPLOAD_URL,
        headers={**auth_headers, "Idempotency-Key": key},
        files={"file": (FILENAME, CONTENT, "image/png")},
        data={
            "latitude": str(LAT),
            "longitude": str(LON),
            "description": description,
            "force_submit": "false",
        },
    )


async def test_replay_returns_stored_response(client, auth_headers) -> None:
    body = _stored_body()
    request_hash = hash_request(USER_ID, LAT, LON, "stored description", False, FILENAME, CONTENT)
    await _insert_record(
        key="replay-key",
        status=IdempotencyStatus.succeeded,
        request_hash=request_hash,
        body=body,
    )

    resp = await _post(client, auth_headers, key="replay-key")

    assert resp.status_code == 200
    assert resp.headers.get("Idempotency-Replayed") == "true"
    assert resp.json() == body


async def test_key_reused_for_different_request_is_400(client, auth_headers) -> None:
    # The stored fingerprint belongs to a *different* body than the one posted.
    original_hash = hash_request(USER_ID, LAT, LON, "original description", False, FILENAME, CONTENT)
    await _insert_record(
        key="conflict-key",
        status=IdempotencyStatus.succeeded,
        request_hash=original_hash,
        body=_stored_body(),
    )

    resp = await _post(client, auth_headers, key="conflict-key", description="a different description")

    assert resp.status_code == 400
    assert "different request" in resp.json()["detail"]


async def test_in_progress_key_is_409(client, auth_headers) -> None:
    request_hash = hash_request(USER_ID, LAT, LON, "stored description", False, FILENAME, CONTENT)
    await _insert_record(
        key="inflight-key",
        status=IdempotencyStatus.in_progress,
        request_hash=request_hash,
    )

    resp = await _post(client, auth_headers, key="inflight-key")

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "IDEMPOTENCY_IN_PROGRESS"
    assert resp.headers.get("Retry-After") == "1"


async def test_oversized_key_is_rejected(client, auth_headers) -> None:
    resp = await _post(client, auth_headers, key="x" * 129)
    assert resp.status_code == 400
    assert "Idempotency-Key" in resp.json()["detail"]
