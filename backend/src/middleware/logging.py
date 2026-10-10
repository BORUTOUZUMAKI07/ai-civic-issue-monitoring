import time
import uuid

import structlog.contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.log_utils import get_logger, log_request_end, log_request_start

logger = get_logger("middleware")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        # Bound once for the whole request, so every log line emitted by any
        # module while handling it carries correlation_id -- including the ~30
        # that call logging.getLogger(__name__) and never pass
        # extra={"correlation_id": ...} themselves. Cleared in `finally` so a
        # failed request cannot leak its id into the next one.
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        try:
            log_request_start(logger, request.method, request.url.path, correlation_id)

            start = time.time()
            response = await call_next(request)
            duration_ms = (time.time() - start) * 1000

            log_request_end(logger, request.method, request.url.path, response.status_code, duration_ms, correlation_id)

            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
