import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [1, 2, 4, 8, 16]

connect_args = {}
if settings.ASYNC_DATABASE_URI.startswith("postgresql"):
    connect_args["statement_cache_size"] = 0

engine = create_async_engine(
    settings.ASYNC_DATABASE_URI,
    echo=False,
    pool_size=20,
    max_overflow=10,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> bool:
    for attempt, delay in enumerate(_RETRY_DELAYS):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connection verified successfully.")
            break
        except Exception as e:
            logger.warning("Database connection attempt %d failed: %s", attempt + 1, e)
            if attempt < len(_RETRY_DELAYS) - 1:
                await asyncio.sleep(delay)
    else:
        logger.error("Database unreachable after %d attempts — serving in degraded mode", len(_RETRY_DELAYS))
        return False

    try:
        from src.models.base import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified.")
    except Exception as e:
        logger.warning("Table creation skipped (may need manual Alembic migration): %s", e)

    return True


async def check_db_health() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
