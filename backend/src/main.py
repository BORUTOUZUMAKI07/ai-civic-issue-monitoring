#!/usr/bin/env python3
"""CivicPulse - AI-Powered Urban Issue Intelligence Platform"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.core.database import check_db_health, engine, init_db
from src.core.mongodb import init_mongodb
from src.core.redis import check_redis_health, init_redis
from src.domains.auth.routes import router as auth_router
from src.domains.dashboard.routes import router as dashboard_router
from src.domains.engineers.routes import router as engineers_router
from src.domains.issues.routes import router as issues_router
from src.domains.notifications.routes import router as notifications_router
from src.domains.resolution.routes import router as resolution_router
from src.domains.wards.routes import router as wards_router
from src.errors.base import AppError
from src.log_utils import setup_logging
from src.middleware import LoggingMiddleware, RateLimitMiddleware, RBACMiddleware

logger = logging.getLogger("civicpulse")


def create_app(lifespan_override=None):
    app = FastAPI(
        title="CivicPulse",
        description="AI-Powered Urban Issue Intelligence Platform",
        version=settings.VERSION,
        lifespan=lifespan_override,
    )

    cors_origins = [settings.FRONTEND_URL]
    if settings.CORS_ORIGINS:
        cors_origins.extend([o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()])
    if settings.ENVIRONMENT == "development":
        cors_origins.append("http://localhost:3000")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RBACMiddleware)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "error_code": exc.error_code},
        )

    @app.get("/health")
    async def health():
        db_ok = await check_db_health()
        redis_ok = await check_redis_health()
        mongo_ok = False
        ml_ok = False
        try:
            from src.core.mongodb import mongodb_initialized

            mongo_ok = mongodb_initialized
        except Exception:
            pass
        try:
            from src.ml.inference.predict import get_model_info

            ml_info = get_model_info()
            ml_ok = ml_info.get("model_exists", False)
        except Exception:
            pass
        status_code = 200 if db_ok and redis_ok else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "healthy" if status_code == 200 else "unhealthy",
                "database": db_ok,
                "redis": redis_ok,
                "mongodb": mongo_ok,
                "ml_model": ml_ok,
            },
        )

    @app.get("/api/v1/ml/info")
    async def ml_info():
        from src.ml.inference.predict import get_model_info

        return get_model_info()

    @app.get("/api/v1/ml/ab-test/stats")
    async def ab_test_stats():
        from src.ml.inference.ab_testing import get_ab_tester

        return get_ab_tester().get_stats()

    @app.get("/api/v1/ml/registry/versions")
    async def model_registry_versions():
        from src.ml.registry import get_model_registry

        return get_model_registry().list_versions()

    @app.get("/api/v1/ml/registry/production")
    async def model_registry_production():
        from src.ml.registry import get_model_registry

        model = get_model_registry().get_production_model()
        if not model:
            return {"detail": "No production model found"}
        return model

    @app.get("/api/v1/ml/registry/compare")
    async def model_registry_compare():
        from src.ml.registry import get_model_registry

        result = get_model_registry().compare_versions()
        if not result:
            return {"detail": "No models to compare"}
        return result

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(issues_router, prefix="/api/v1")
    app.include_router(wards_router, prefix="/api/v1")
    app.include_router(engineers_router, prefix="/api/v1")
    app.include_router(resolution_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")

    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

    return app


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting CivicPulse...")

    try:
        await init_db()
        logger.info("Database connected.")
    except Exception as e:
        logger.warning("Database connection failed: %s", e)

    try:
        await init_redis()
        logger.info("Redis connected.")
    except Exception as e:
        logger.warning("Redis connection failed: %s", e)

    try:
        await init_mongodb()
        logger.info("MongoDB connected.")
    except Exception as e:
        logger.warning("MongoDB connection failed: %s", e)

    try:
        from src.ml.inference.predict import get_model_info

        ml_info = get_model_info()
        logger.info("ML Model loaded: %s (%s MB)", ml_info["model_path"], ml_info["model_size_mb"])
    except Exception as e:
        logger.warning("ML Model loading failed: %s", e)

    yield

    from src.core.mongodb import close_mongodb

    await close_mongodb()
    await engine.dispose()
    logger.info("Shutdown complete.")


app = create_app(lifespan_override=lifespan)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=port, reload=False, access_log=False)
