from src.errors.common import BadRequestError, ConflictError, NotFoundError, UnauthorizedError


class EmailAlreadyExists(ConflictError):
    def __init__(self):
        super().__init__(detail="Email already registered.")


class OAuthNotConfigured(BadRequestError):
    def __init__(self, provider: str):
        super().__init__(detail=f"{provider} OAuth is not configured.")


class OAuthError(BadRequestError):
    def __init__(self, detail: str = "OAuth sign-in failed."):
        super().__init__(detail=detail)


class OAuthStateInvalid(BadRequestError):
    def __init__(self):
        super().__init__(detail="Invalid OAuth state.")


class PasswordResetTokenInvalid(UnauthorizedError):
    def __init__(self, detail: str = "Password reset token is invalid or has expired."):
        super().__init__(detail=detail)


class PasswordResetEmailNotSent(BadRequestError):
    def __init__(self, detail: str = "Password reset email could not be sent. Please try again later."):
        super().__init__(detail=detail)


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
