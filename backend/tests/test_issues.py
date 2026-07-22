from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_issues(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get("/api/v1/issues", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_list_issues_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/api/v1/issues")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_issue_not_found(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get("/api/v1/issues/99999", headers=auth_headers)
    assert response.status_code == 404
