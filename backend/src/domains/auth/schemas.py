from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "field_worker"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: str
    two_factor_enabled: bool = False


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
