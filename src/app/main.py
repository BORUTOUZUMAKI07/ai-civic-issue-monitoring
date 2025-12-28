from fastapi import FastAPI, UploadFile, File, Form
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.core.logging import setup_logging
from app.utils.exceptions import register_exception_handlers
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_fastapi_instrumentator import Instrumentator

limiter = Limiter(key_func=get_remote_address)

def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-Based Civic Issue Monitoring System",
        version="0.1.0",
    )

    setup_logging()
    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # In prod, specify the actual domain
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    # Rate Limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Monitoring
    Instrumentator().instrument(app).expose(app)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
