from src.errors.common import BadRequestError, ConflictError, NotFoundError, UnauthorizedError


class EmailAlreadyExists(ConflictError):
    def __init__(self):
        super().__init__(detail="Email already registered.")


class InvalidCredentials(UnauthorizedError):
    def __init__(self):
        super().__init__(detail="Incorrect email or password.")


class TokenExpired(UnauthorizedError):
    def __init__(self):
        super().__init__(detail="Token has expired.")


class TokenRevoked(UnauthorizedError):
    def __init__(self):
        super().__init__(detail="Token has been revoked.")


class InvalidToken(UnauthorizedError):
    def __init__(self):
        super().__init__(detail="Invalid or expired token.")


class UserNotFound(NotFoundError):
    def __init__(self):
        super().__init__(detail="User not found.")
