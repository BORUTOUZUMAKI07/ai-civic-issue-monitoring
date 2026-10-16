#!/usr/bin/env python3
"""CivicPulse - AI-Powered Urban Issue Intelligence Platform"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import src.models  # noqa: F401 — register every ORM model on Base.metadata
from src.core.config import settings
from src.core.database import check_db_health, engine, init_db
from src.core.mongodb import init_mongodb
from src.core.observability import (
    setup_otlp_metrics,
    setup_otlp_tracing,
    shutdown_otlp_log_handler,
    shutdown_otlp_metrics,
    shutdown_otlp_tracing,
)
from src.core.redis import check_redis_health, init_redis
from src.domains.admin.api.routes import router as admin_router
from src.domains.auth.api.routes import router as auth_router
from src.domains.dashboard.api.routes import router as dashboard_router
from src.domains.engineers.api.routes import router as engineers_router
from src.domains.issues.api.routes import router as issues_router
from src.domains.ml.api.routes import router as ml_router
from src.domains.notifications.api.routes import router as notifications_router
from src.domains.resolution.api.routes import router as resolution_router
from src.domains.wards.api.routes import router as wards_router
from src.log_utils import setup_logging
from src.middleware import LoggingMiddleware, OTelMetricsMiddleware, RateLimitMiddleware, RBACMiddleware
from src.shared.errors.base import AppError

logger = logging.getLogger("civicpulse")


async def _collect_health() -> tuple[bool, dict[str, bool]]:
    """Dependency-aware health snapshot shared by /health and /health/ready.

    ``ready`` is the only value that should gate traffic: it is true when the
    datastores the request path needs (Postgres, Redis) answer. MongoDB and the
    ML model are reported but do not gate -- both are optional subsystems that
    degrade rather than fail a request.
    """
    db_ok = await check_db_health()
    redis_ok = await check_redis_health()
    mongo_ok = False
    ml_ok = False
    try:
        from src.core.mongodb import mongodb_initialized

        mongo_ok = bool(mongodb_initialized)
    except Exception:  # optional subsystem absent -> reported as down  # nosec B110
        pass
    try:
        from src.ml.inference.predict import get_model_info

        ml_info = get_model_info()
        ml_ok = bool(ml_info.get("model_exists", False))
    except Exception:  # optional subsystem absent -> reported as down  # nosec B110
        pass
    ready = db_ok and redis_ok
    return ready, {
        "database": db_ok,
        "redis": redis_ok,
        "mongodb": mongo_ok,
        "ml_model": ml_ok,
    }


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
    # Added after the app's own middleware, so it wraps the rate-limit and RBAC
    # layers and the router: RED metrics then cover throttled (429) and rejected
    # (401/403) requests too, not just the ones that reach a handler. (The trace
    # instrumentor wired below is added even later, so it stays outermost.)
    # Recording is a no-op until setup_otlp_metrics() wires a provider, so an
    # unconfigured app pays nothing.
    app.add_middleware(OTelMetricsMiddleware)

    # Layer-1 -> Layer-2 export. Wired at build time so the global providers
    # exist before the first request; a strict no-op unless NEW_RELIC_ENABLED is
    # set, and fail-open (a missing [observability] extra just logs). All three
    # signals share one OTLP pipeline -- logs (src/log_utils), traces (the
    # FastAPI/httpx/SQLAlchemy instrumentors) and metrics (OTelMetricsMiddleware).
    setup_otlp_tracing(app)
    setup_otlp_metrics()

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "error_code": exc.error_code},
        )

    @app.get("/health/live")
    async def health_live():
        # Liveness: is the process up? Deliberately does NOT touch a datastore,
        # so a transient dependency blip cannot make an orchestrator kill a
        # healthy worker -- the mistake that turns a slow dependency into an
        # outage by restart-looping the whole fleet.
        return JSONResponse(status_code=200, content={"status": "alive"})

    @app.get("/health/ready")
    async def health_ready():
        # Readiness: should this instance take traffic? Reflects dependency
        # health, so a not-yet-connected instance is pulled from rotation
        # without being restarted.
        ready, components = await _collect_health()
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "not_ready", **components},
        )

    @app.get("/health")
    async def health():
        # Kept as the detailed, dependency-aware probe that the Docker
        # HEALTHCHECK, the deploy workflow and existing clients already call.
        # `/health/live` and `/health/ready` are the split probes for platform
        # orchestrators; `/health` stays the union of the two for back-compat.
        ready, components = await _collect_health()
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "healthy" if ready else "unhealthy", **components},
        )

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(issues_router, prefix="/api/v1")
    app.include_router(wards_router, prefix="/api/v1")
    app.include_router(engineers_router, prefix="/api/v1")
    app.include_router(resolution_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(ml_router, prefix="/api/v1")

    # NOTE: uploads are served by the authenticated route
    # ``GET /api/v1/issues/media/{path}`` rather than a public static mount.
    # Mounting ``uploads/`` at ``/uploads`` handed every photo to unauthenticated
    # callers; images are fetched through the same cookie-authenticated proxy as
    # the rest of the API, so access can be revoked by logging the user out.
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)

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

    # Preload the ML model before accepting traffic: the first /issues/upload
    # must never pay the load cost or race another request that is loading.
    # Runs in a worker thread (the load is sync/CPU-bound); fail-open, so a
    # missing artifact or a transient failure just defers to the lazy path.
    try:
        from src.ml.inference.predict import warmup_model

        await asyncio.to_thread(warmup_model)
    except Exception as e:
        logger.warning("ML model warmup failed (first request will lazy-load): %s", e)

    yield

    from src.core.mongodb import close_mongodb

    await close_mongodb()
    await engine.dispose()
    shutdown_otlp_log_handler()
    shutdown_otlp_tracing()
    shutdown_otlp_metrics()
    logger.info("Shutdown complete.")


app = create_app(lifespan_override=lifespan)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",  # container entrypoint must listen on every interface  # nosec B104
        port=port,
        reload=False,
        access_log=False,
    )
