"""Direct-upload objects are untrusted until validated; reads must be bounded."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core import storage


@pytest.mark.asyncio
async def test_local_bounded_read_stops_at_the_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(storage, "settings", SimpleNamespace(STORAGE_BACKEND="local"))

    target = storage._local_path("issues/huge.jpg")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x" * 64)

    data = await storage.get_upload_bounded("/uploads/issues/huge.jpg", limit=10)
    assert data == b"x" * 10


@pytest.mark.asyncio
async def test_local_bounded_read_reports_a_missing_object(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(storage, "settings", SimpleNamespace(STORAGE_BACKEND="local"))

    with pytest.raises(storage.UploadNotFoundError):
        await storage.get_upload_bounded("/uploads/issues/missing.jpg", limit=10)


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.read_limit: int | None = None
        self.closed = False

    def read(self, limit: int = -1) -> bytes:
        self.read_limit = limit
        return self.data[:limit]

    def close(self) -> None:
        self.closed = True


class _FakeClient:
    def __init__(self, body: _FakeBody) -> None:
        self.body = body
        self.get_calls: list[dict] = []

    def get_object(self, **kwargs) -> dict:
        self.get_calls.append(kwargs)
        return {"Body": self.body}


def _use_s3(monkeypatch, client: object) -> None:
    monkeypatch.setattr(
        storage,
        "settings",
        SimpleNamespace(STORAGE_BACKEND="s3", NEON_STORAGE_BUCKET="bucket"),
    )
    monkeypatch.setattr(storage, "_s3_client", lambda: client)


@pytest.mark.asyncio
async def test_s3_bounded_read_passes_the_limit_and_closes_the_body(monkeypatch):
    body = _FakeBody(b"y" * 64)
    client = _FakeClient(body)
    _use_s3(monkeypatch, client)

    data = await storage.get_upload_bounded("/uploads/issues/huge.jpg", limit=10)

    assert data == b"y" * 10
    assert body.read_limit == 10
    assert body.closed is True
    assert client.get_calls == [{"Bucket": "bucket", "Key": "issues/huge.jpg"}]


@pytest.mark.asyncio
async def test_s3_bounded_read_defaults_to_the_validation_cap(monkeypatch):
    body = _FakeBody(b"z")
    _use_s3(monkeypatch, _FakeClient(body))

    await storage.get_upload_bounded("/uploads/issues/a.jpg")

    assert body.read_limit == storage.MAX_UPLOAD_BYTES + 1
    assert body.closed is True


@pytest.mark.asyncio
async def test_s3_bounded_read_maps_no_such_key(monkeypatch):
    class _MissingKey(Exception):
        def __init__(self) -> None:
            super().__init__("The specified key does not exist.")
            self.response = {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}

    class _MissingClient:
        def get_object(self, **kwargs):
            raise _MissingKey()

    _use_s3(monkeypatch, _MissingClient())

    with pytest.raises(storage.UploadNotFoundError):
        await storage.get_upload_bounded("/uploads/issues/x.jpg", limit=10)


@pytest.mark.asyncio
async def test_s3_bounded_read_propagates_unexpected_failures(monkeypatch):
    class _BrokenClient:
        def get_object(self, **kwargs):
            raise RuntimeError("unexpected")

    _use_s3(monkeypatch, _BrokenClient())

    # No S3 error metadata is attached, so a genuinely unexpected failure must
    # still propagate rather than being silently treated as "not found".
    with pytest.raises(RuntimeError, match="unexpected"):
        await storage.get_upload_bounded("/uploads/issues/x.jpg", limit=10)
