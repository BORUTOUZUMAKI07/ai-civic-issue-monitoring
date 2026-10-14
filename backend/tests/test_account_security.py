from __future__ import annotations

from httpx import AsyncClient

from src.core.security import decode_token


async def test_change_password_success_and_rotation(client: AsyncClient) -> None:
    email = "change-pw-ok@civicpulse.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "OldPass123!", "full_name": "Change Pw"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "OldPass123!"}
    )
    assert login.status_code == 200

    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "OldPass123!", "new_password": "NewPass456!"},
    )
    assert changed.status_code == 200

    # The old password must no longer authenticate; the new one must.
    old = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "OldPass123!"}
    )
    assert old.status_code in (401, 404)
    new = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "NewPass456!"}
    )
    assert new.status_code == 200


async def test_change_password_rejects_wrong_current(client: AsyncClient) -> None:
    email = "change-pw-bad@civicpulse.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "OldPass123!", "full_name": "Change Pw Bad"},
    )
    await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "OldPass123!"}
    )
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "WrongPass999!", "new_password": "NewPass456!"},
    )
    assert resp.status_code == 401


async def test_change_password_requires_authentication(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": "NewPass456!"},
    )
    assert resp.status_code == 401


async def test_ws_ticket_is_ws_scoped(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.get("/api/v1/auth/ws-ticket", headers=auth_headers)
    assert resp.status_code == 200
    ticket = resp.json()["ticket"]
    payload = decode_token(ticket)
    assert payload["type"] == "ws"
    assert payload["sub"] == "1"


async def test_ws_ticket_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/ws-ticket")
    assert resp.status_code == 401
