"""Authenticated media reads must not buffer an arbitrarily large object."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.core import storage
from src.domains.issues.api import routes as issue_routes

_USER = SimpleNamespace()


@pytest.mark.asyncio
async def test_media_route_uses_the_bounded_reader(monkeypatch) -> None:
    keys: list[str] = []

    async def bounded(key: str) -> bytes:
        keys.append(key)
        return b"image-bytes"

    monkeypatch.setattr(issue_routes, "get_upload_bounded", bounded)

    response = await issue_routes.serve_media("issues/a.jpg", user=_USER)  # type: ignore[arg-type]

    assert response.status_code == 200
    assert response.body == b"image-bytes"
    assert keys == ["issues/a.jpg"]


@pytest.mark.asyncio
async def test_media_route_refuses_an_oversized_object(monkeypatch) -> None:
    async def oversized(key: str) -> bytes:
        assert key == "issues/huge.jpg"
        return b"x" * (storage.MAX_UPLOAD_BYTES + 1)

    monkeypatch.setattr(issue_routes, "get_upload_bounded", oversized)

    with pytest.raises(HTTPException) as exc:
        await issue_routes.serve_media("issues/huge.jpg", user=_USER)  # type: ignore[arg-type]

    assert exc.value.status_code == 404
    assert exc.value.detail == "Not found."
