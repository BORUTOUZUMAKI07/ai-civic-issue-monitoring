from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_health_returns_components(client: AsyncClient) -> None:
    response = await client.get("/health")
    data = response.json()
    assert "database" in data
    assert "redis" in data
    assert "mongodb" in data


@pytest.mark.asyncio
async def test_health_live_is_dependency_free(client: AsyncClient) -> None:
    # Liveness must answer 200 without touching a datastore, so a dependency
    # blip cannot make an orchestrator restart a healthy process.
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_health_ready_reports_dependencies(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["status"] in ("ready", "not_ready")
    assert "database" in data
    assert "redis" in data


@pytest.mark.asyncio
async def test_health_ready_does_not_gate_on_redis(client: AsyncClient) -> None:
    # Redis is fail-open everywhere in this codebase, so its loss degrades
    # revocation and rate limiting but never breaks a request. Readiness must
    # therefore stay green with Postgres up, rather than pulling a working API
    # out of rotation — Redis is still reported for the operator to see.
    with patch("src.main.check_db_health", AsyncMock(return_value=True)):
        with patch("src.main.check_redis_health", AsyncMock(return_value=False)):
            response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] is True
    assert data["redis"] is False


@pytest.mark.asyncio
async def test_openapi_schema(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "paths" in data
