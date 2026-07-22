from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@civicpulse.com",
            "password": "TestPass123!",
            "full_name": "New User",
        },
    )
    assert response.status_code in (200, 201, 409)


@pytest.mark.asyncio
async def test_register_user_invalid_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid-email",
            "password": "TestPass123!",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@civicpulse.com",
            "password": "WrongPass123!",
        },
    )
    assert response.status_code in (401, 404)
