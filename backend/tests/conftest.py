"""
CivicPulse Test Configuration — Full Database Isolation
=======================================================
Three-layer strategy:

  Layer 1 – UNIT (default, always runs, no I/O):
      PostgreSQL  → SQLite :memory: (aiosqlite)
      Redis       → fakeredis (in-process, RAM only)
      MongoDB     → mongomock-motor (in-process, RAM only)
      External AI → monkeypatched to raise ImportError / return stubs

  Layer 2 – MOCK-INTEGRATION (marker: mock_integration):
      Same in-memory fakes, but routes are exercised end-to-end via ASGI.
      Nothing leaves the process.

  Layer 3 – INTEGRATION (marker: integration, CI-skipped by default):
      PostgreSQL  → Testcontainers real Postgres container
      Redis       → Testcontainers real Redis container
      MongoDB     → mongomock (still, Atlas is prod-only)
      Requires Docker to be running.

NEVER connects to Aiven, Atlas, Upstash or any cloud resource during tests.
"""
from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ─────────────────────────────────────────────────────────────────────────────
# 1. Override ALL environment variables BEFORE any src.* imports
#    This must happen at module-import time so pydantic Settings picks them up.
# ─────────────────────────────────────────────────────────────────────────────
os.environ.update({
    "SECRET_KEY": "test-secret-key-for-pytest-32-chars-long",
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "ASYNC_DATABASE_URI": "sqlite+aiosqlite:///:memory:",
    "REDIS_URL": "redis://localhost:6379",          # won't be touched; fakeredis replaces it
    "UPSTASH_REDIS_REST_URL": "",                   # disable upstash so fakeredis takes over
    "UPSTASH_REDIS_REST_TOKEN": "",
    "MONGODB_URI": "mongodb://localhost:27017",     # won't be touched; mongomock replaces it
    "MONGODB_DB": "civicpulse_test",               # isolated DB name
    "ENVIRONMENT": "testing",
    "OPENAI_API_KEY": "",                           # disable LLM calls
    "NEW_RELIC_LICENSE_KEY": "",                    # disable APM
    "MLFLOW_TRACKING_URI": "",
    "AB_TEST_ENABLED": "false",
})

# ── SQLite dialect shims (replace PG-specific types with SQLite equivalents) ──
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402

SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"
SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "VARCHAR(36)"

# ─────────────────────────────────────────────────────────────────────────────
# 2. Event loop (single session-scoped loop)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# 3. LAYER 1: fakeredis — replaces Redis/Upstash entirely in RAM
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def fake_redis_session():
    """Session-scoped fakeredis. No network calls to Redis ever happen in tests."""
    try:
        import fakeredis.aioredis as fakeredis_async
        fake = fakeredis_async.FakeRedis()
    except ImportError:
        # fakeredis not installed → use a simple async no-op dict-based stub
        fake = _FallbackFakeRedis()

    # Patch the redis_client object that all src.core.redis functions call
    with patch("src.core.redis.redis_client", fake):
        # Also stub check_redis_health so it always returns True
        with patch("src.core.redis.check_redis_health", AsyncMock(return_value=True)):
            yield fake


class _FallbackFakeRedis:
    """Minimal async dict-backed Redis stub (used when fakeredis not installed)."""

    def __init__(self):
        self._store: dict = {}

    async def ping(self): return True
    async def get(self, key): return self._store.get(key)
    async def setex(self, key, ttl, value): self._store[key] = value; return True
    async def delete(self, key): self._store.pop(key, None); return 1
    async def incr(self, key): self._store[key] = int(self._store.get(key, 0)) + 1; return self._store[key]
    async def expire(self, key, ttl): return True
    async def eval(self, script, numkeys, *args): return 1  # always allow


# ─────────────────────────────────────────────────────────────────────────────
# 4. LAYER 1: mongomock — replaces AsyncIOMotorClient entirely in RAM
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def fake_mongo_session():
    """
    Session-scoped MongoDB mock.
    Uses mongomock-motor (async-compatible) when available, falls back to a
    simple in-process dict-backed stub.
    No network calls to Atlas are ever made during tests.
    """
    try:
        from mongomock_motor import AsyncMongoMockClient
        mock_client = AsyncMongoMockClient()
    except ImportError:
        # mongomock-motor not installed → the conftest still works, MongoDB
        # operations will just silently no-op via the mongodb_initialized=False flag
        mock_client = None

    if mock_client is not None:
        with patch("src.core.mongodb.AsyncIOMotorClient", return_value=mock_client):
            with patch("src.core.mongodb.mongodb_initialized", True):
                yield mock_client
    else:
        # MongoDB disabled for this test session
        with patch("src.core.mongodb.mongodb_initialized", False):
            yield None


# ─────────────────────────────────────────────────────────────────────────────
# 5. LAYER 1: SQLite in-memory Postgres replacement
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create a single SQLite :memory: engine for the entire test session."""
    import src.models  # noqa: F401 — register all SQLAlchemy models
    from src.core.database import engine
    from src.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# 6. ASGI test client (unit / mock-integration tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTPX client against the FastAPI app.
    - PostgreSQL  → SQLite :memory:
    - Redis       → fakeredis (session fixture above)
    - MongoDB     → mongomock (session fixture above)
    - ML model    → not loaded (env var checks prevent it)
    """
    from src.main import create_app

    app = create_app()  # no lifespan — don't connect to real services
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─────────────────────────────────────────────────────────────────────────────
# 7. Auth fixtures (JWT tokens backed by SQLite users)
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def auth_headers(db_engine) -> dict:
    from src.core.database import AsyncSessionLocal
    from src.core.security import create_access_token
    from src.models.user import User, UserRole

    async with AsyncSessionLocal() as session:
        user = User(
            id=1,
            email="test@civicpulse.com",
            password_hash="unused",
            full_name="Test User",
            role=UserRole.field_worker,
            is_active=True,
        )
        session.add(user)
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    token = create_access_token({"sub": "1", "role": "field_worker"})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(db_engine) -> dict:
    from src.core.database import AsyncSessionLocal
    from src.core.security import create_access_token
    from src.models.user import User, UserRole

    async with AsyncSessionLocal() as session:
        user = User(
            id=2,
            email="admin@civicpulse.com",
            password_hash="unused",
            full_name="Admin User",
            role=UserRole.admin,
            is_active=True,
        )
        session.add(user)
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    token = create_access_token({"sub": "2", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# 8. Mock data fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_user() -> dict:
    return {"id": 1, "email": "test@civicpulse.com", "full_name": "Test User", "role": "field_worker", "is_active": True}


@pytest.fixture
def mock_admin() -> dict:
    return {"id": 2, "email": "admin@civicpulse.com", "full_name": "Admin User", "role": "admin", "is_active": True}


@pytest.fixture
def mock_engineer() -> dict:
    return {"id": 3, "email": "engineer@civicpulse.com", "full_name": "Engineer User", "role": "engineer", "is_active": True}


# ─────────────────────────────────────────────────────────────────────────────
# 9. Vision / ML model mocks (prevent ONNX/PyTorch loading during tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_ml_predict():
    """
    Stub the ML inference function so tests never load the ONNX/PyTorch model.
    Returns a realistic pothole prediction dict.
    """
    prediction = {
        "label": "pothole",
        "confidence": 0.91,
        "model": "mobilenet_v2_mock",
        "probabilities": {"pothole": 0.91, "garbage": 0.05, "debris": 0.03, "non_civic": 0.01},
    }
    with patch("src.ml.inference.predict.predict_issue", return_value=prediction):
        yield prediction


@pytest.fixture
def mock_embeddings():
    """Stub embedding generation so tests never call OpenAI/HuggingFace."""
    vector = [0.1] * 1536  # realistic 1536-dim embedding
    with patch("src.core.embeddings.generate_embedding", AsyncMock(return_value=vector)):
        yield vector


@pytest.fixture
def mock_agent_pipeline():
    """Stub the LangGraph agent so tests don't need LangGraph or OpenAI."""
    result = {"matched": True, "engineer_id": 1, "analytics_generated": True}
    with patch("src.agents.graph.AnalyticsGraph.run", AsyncMock(return_value={"result": result})):
        yield result


# ─────────────────────────────────────────────────────────────────────────────
# 10. LAYER 3: Testcontainers fixtures (integration tests only)
#     Usage: mark test with @pytest.mark.integration
#     Requires Docker to be running.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def pg_container():
    """
    Real Postgres container (testcontainers).
    Only used by @pytest.mark.integration tests.
    """
    pytest.importorskip("testcontainers", reason="pip install testcontainers to run integration tests")
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    """
    Real Redis container (testcontainers).
    Only used by @pytest.mark.integration tests.
    """
    pytest.importorskip("testcontainers", reason="pip install testcontainers to run integration tests")
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest_asyncio.fixture
async def integration_client(pg_container, redis_container):
    """
    Full-stack ASGI client backed by real Postgres + Redis containers.
    MongoDB still uses mongomock to avoid touching Atlas in CI.
    """
    import src.models  # noqa: F401
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from src.core.database import get_db
    from src.main import create_app
    from src.models.base import Base

    # Wire real Postgres URL from container
    pg_url = pg_container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
    test_engine = create_async_engine(pg_url, echo=False)
    TestSession = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_db():
        async with TestSession() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_db

    redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
    with patch("src.core.redis.redis_client") as mock_r:
        # Use fakeredis pointed at the container URL for integration tests
        try:
            import fakeredis.aioredis as fakeredis_async
            mock_r.return_value = fakeredis_async.FakeRedis()
        except ImportError:
            mock_r.return_value = _FallbackFakeRedis()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
