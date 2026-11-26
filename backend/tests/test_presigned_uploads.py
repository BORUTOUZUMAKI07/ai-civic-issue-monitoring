"""Direct-upload presign handshake and signed handoff token tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.storage import UploadTokenError, create_upload_token, verify_upload_token
from src.domains.uploads.api import routes


@pytest.mark.asyncio
async def test_presign_returns_signed_put_for_one_random_key(monkeypatch, client, auth_headers):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(STORAGE_BACKEND="s3"))

    def fake_presign(image_url: str, *, content_type: str | None = None) -> dict:
        return {"url": f"https://storage.example/{image_url.lstrip('/')}", "expires_in": 900, "content_type": content_type}

    monkeypatch.setattr(routes, "presign_put_upload", fake_presign)

    res = await client.post(
        "/api/v1/uploads/presign",
        json={"filename": "pothole.jpg", "purpose": "issue", "size": 1024},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["method"] == "PUT"
    assert data["image_url"].startswith("/uploads/issues/")
    assert data["image_url"].endswith(".jpg")
    assert data["required_headers"] == {"Content-Type": "image/jpeg"}
    assert data["expires_in"] == 900
    assert data["upload_url"].endswith(data["image_url"])

    # Token is bound to key + user + purpose; it cannot be replayed elsewhere.
    verify_upload_token(data["upload_token"], data["image_url"], 1, "issue")
    with pytest.raises(UploadTokenError):
        verify_upload_token(data["upload_token"], data["image_url"], 2, "issue")
    with pytest.raises(UploadTokenError):
        verify_upload_token(data["upload_token"], data["image_url"], 1, "resolution")


@pytest.mark.asyncio
async def test_presign_is_stable_for_the_same_idempotency_key(monkeypatch, client, auth_headers):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(STORAGE_BACKEND="s3"))
    monkeypatch.setattr(
        routes,
        "presign_put_upload",
        lambda image_url, *, content_type=None: {"url": "https://storage.example/put", "expires_in": 900, "content_type": content_type},
    )

    body = {
        "filename": "pothole.png",
        "purpose": "issue",
        "size": 2048,
        "idempotency_key": "client-generated-key",
    }
    first = await client.post("/api/v1/uploads/presign", json=body, headers=auth_headers)
    second = await client.post("/api/v1/uploads/presign", json=body, headers=auth_headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["image_url"] == second.json()["image_url"]
    for response in (first, second):
        verify_upload_token(response.json()["upload_token"], response.json()["image_url"], 1, "issue")


@pytest.mark.asyncio
async def test_presign_rejects_bad_extension_and_oversize(client, auth_headers):
    bad_ext = await client.post(
        "/api/v1/uploads/presign",
        json={"filename": "payload.svg", "purpose": "issue"},
        headers=auth_headers,
    )
    assert bad_ext.status_code == 400

    too_large = await client.post(
        "/api/v1/uploads/presign",
        json={"filename": "big.jpg", "purpose": "issue", "size": 6 * 1024 * 1024},
        headers=auth_headers,
    )
    assert too_large.status_code == 400


@pytest.mark.asyncio
async def test_local_backend_has_no_presign(monkeypatch, client, auth_headers):
    # Force local mode: a developer's backend/.env may already select s3.
    monkeypatch.setattr(routes, "settings", SimpleNamespace(STORAGE_BACKEND="local"))
    res = await client.post(
        "/api/v1/uploads/presign",
        json={"filename": "pothole.jpg", "purpose": "issue"},
        headers=auth_headers,
    )
    assert res.status_code == 501


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setattr("src.core.storage.time.time", lambda: 1_000_000)
    token = create_upload_token("/uploads/issues/x.jpg", 1, "issue")
    monkeypatch.setattr("src.core.storage.time.time", lambda: 1_000_000 + 901)
    with pytest.raises(UploadTokenError):
        verify_upload_token(token, "/uploads/issues/x.jpg", 1, "issue")
