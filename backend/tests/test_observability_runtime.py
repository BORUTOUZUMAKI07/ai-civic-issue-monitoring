"""Runtime observability guards: startup proof, browser error intake, 500 logs."""

from __future__ import annotations

import logging
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.config import settings
from src.core.observability import get_startup_telemetry_status, verify_startup_telemetry
from src.middleware.logging import LoggingMiddleware


def test_startup_verification_is_fail_open_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEW_RELIC_ENABLED", False)
    result = verify_startup_telemetry()
    assert result["status"] == "disabled"
    assert result["telemetry_ok"] is False
    assert result["traces_ok"] is False
    assert get_startup_telemetry_status() == result


@pytest.mark.asyncio
async def test_health_telemetry_endpoint_is_diagnostic(client: AsyncClient) -> None:
    response = await client.get("/health/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded", "disabled", "not_checked"}
    assert "telemetry_ok" in data


@pytest.mark.asyncio
async def test_client_error_endpoint_scrubs_credentials(client: AsyncClient, caplog) -> None:
    payload = {
        "event_type": "api_error",
        "message": "Login failed token=supersecret Bearer abcdefgh1234",
        "api_path": "/api/v1/auth/login?code=one-time-code",
        "method": "POST",
        "status_code": 401,
        "stack": "Error: password=hunter2\n  at login",
    }
    with caplog.at_level(logging.ERROR, logger="civicpulse.frontend"):
        response = await client.post("/api/v1/observability/client-errors", json=payload)

    assert response.status_code == 202
    log = next(record for record in caplog.records if getattr(record, "event_type", None) == "frontend_error")
    assert "***REDACTED***" in log.getMessage()
    assert "supersecret" not in log.getMessage()
    assert "hunter2" not in log.error_stack
    assert "abcdefgh1234" not in log.getMessage()
    assert "code=one-time-code" not in log.api_path


@pytest.mark.asyncio
async def test_unhandled_exception_has_structured_request_log(caplog) -> None:
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with caplog.at_level(logging.ERROR, logger="civicpulse.middleware"):
            response = await client.get("/boom", headers={"X-Correlation-ID": "caller-id"})

    assert response.status_code == 500
    log = next(record for record in caplog.records if getattr(record, "event_type", None) == "request_exception")
    assert "Unhandled request exception" in log.getMessage()
    assert log.http_status_code == 500
    # A malformed caller ID must not reach logs; a valid one is preserved.
    assert log.correlation_id != "caller-id"
    uuid.UUID(log.correlation_id)


@pytest.mark.asyncio
async def test_valid_correlation_id_is_returned_to_caller() -> None:
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    supplied = str(uuid.uuid4())
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ok", headers={"X-Correlation-ID": supplied})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == supplied
