from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ["SECRET_KEY"] = "test-secret-key-for-pytest"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test.db"
os.environ["ASYNC_DATABASE_URI"] = "sqlite+aiosqlite:///test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["ENVIRONMENT"] = "testing"

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    import src.models  # noqa: F401 — register all models
    from src.core.database import engine
    from src.main import create_app
    from src.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mock_user() -> dict:
    return {
        "id": 1,
        "email": "test@civicpulse.com",
        "full_name": "Test User",
        "role": "field_worker",
        "is_active": True,
    }


@pytest.fixture
def mock_admin() -> dict:
    return {
        "id": 2,
        "email": "admin@civicpulse.com",
        "full_name": "Admin User",
        "role": "admin",
        "is_active": True,
    }


@pytest.fixture
def mock_engineer() -> dict:
    return {
        "id": 3,
        "email": "engineer@civicpulse.com",
        "full_name": "Engineer User",
        "role": "engineer",
        "is_active": True,
    }


@pytest_asyncio.fixture
async def auth_headers() -> dict:
    from src.core.database import AsyncSessionLocal
    from src.core.security import create_access_token
    from src.models.user import User, UserRole

    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=1,
                email="test@civicpulse.com",
                password_hash="unused",
                full_name="Test User",
                role=UserRole.field_worker,
                is_active=True,
            )
        )
        await session.commit()

    token = create_access_token({"sub": "1", "role": "field_worker"})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers() -> dict:
    from src.core.database import AsyncSessionLocal
    from src.core.security import create_access_token
    from src.models.user import User, UserRole

    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=2,
                email="admin@civicpulse.com",
                password_hash="unused",
                full_name="Admin User",
                role=UserRole.admin,
                is_active=True,
            )
        )
        await session.commit()

    token = create_access_token({"sub": "2", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}
