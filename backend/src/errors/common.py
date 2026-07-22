from src.errors.base import AppError


class NotFoundError(AppError):
    def __init__(self, detail: str = "Resource not found."):
        super().__init__(detail=detail, status_code=404, error_code="NOT_FOUND")


class ConflictError(AppError):
    def __init__(self, detail: str = "Resource already exists."):
        super().__init__(detail=detail, status_code=409, error_code="CONFLICT")


class BadRequestError(AppError):
    def __init__(self, detail: str = "Bad request."):
        super().__init__(detail=detail, status_code=400, error_code="BAD_REQUEST")


class ForbiddenError(AppError):
    def __init__(self, detail: str = "Access denied."):
        super().__init__(detail=detail, status_code=403, error_code="FORBIDDEN")


class UnauthorizedError(AppError):
    def __init__(self, detail: str = "Not authenticated."):
        super().__init__(detail=detail, status_code=401, error_code="UNAUTHORIZED")


class RateLimitError(AppError):
    def __init__(self, detail: str = "Rate limit exceeded. Try again later."):
        super().__init__(detail=detail, status_code=429, error_code="RATE_LIMITED")


class InternalError(AppError):
    def __init__(self, detail: str = "Internal server error."):
        super().__init__(detail=detail, status_code=500, error_code="INTERNAL_ERROR")
