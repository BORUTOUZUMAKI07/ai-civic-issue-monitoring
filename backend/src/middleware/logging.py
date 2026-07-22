import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.log_utils import get_logger, log_request_end, log_request_start

logger = get_logger("middleware")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        log_request_start(logger, request.method, request.url.path, correlation_id)

        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        log_request_end(logger, request.method, request.url.path, response.status_code, duration_ms, correlation_id)

        response.headers["X-Correlation-ID"] = correlation_id
        return response
