from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str
    role: str = "field_worker"


class OauthExchangeRequest(BaseModel):
    # One-time code handed to the frontend by the OAuth callback. Bounds stop a
    # caller from probing arbitrary Redis keys with oversized input.
    code: str = Field(min_length=16, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    current_password: str
    # Matches the client-side floor in ``frontend/src/lib/schemas.ts``.
    new_password: str = Field(min_length=6, max_length=128)


class WsTicketResponse(BaseModel):
    ticket: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: str
    two_factor_enabled: bool = False
    email_verified: bool = True


class TwoFactorVerifyRequest(BaseModel):
    challenge: str
    code: str


class TwoFactorConfirmRequest(BaseModel):
    code: str


class TwoFactorEnableResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TwoFactorRecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]
