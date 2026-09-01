from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    is_token_blacklisted,
    verify_password,
)
from src.errors import (
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidToken,
    TokenRevoked,
    UnauthorizedError,
    UserNotFound,
)
from src.models.user import User, UserRole
from src.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def register(self, email: str, password: str, full_name: str, role: str = "field_worker") -> User:
        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise EmailAlreadyExists()

        user_role = UserRole(role) if role in [r.value for r in UserRole] else UserRole.field_worker
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=user_role,
        )
        return await self.user_repo.create(user)

    async def login(self, email: str, password: str) -> tuple[str, str]:
        user = await self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise InvalidCredentials()
        if not user.is_active:
            raise UnauthorizedError(detail="Account is deactivated.")

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        return access_token, refresh_token

    async def refresh(self, refresh_token: str) -> tuple[str, str]:
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise InvalidToken()

        if payload.get("type") != "refresh":
            raise InvalidToken()

        jti = payload.get("jti")
        family = payload.get("family")

        if jti and await is_token_blacklisted(jti):
            if family:
                ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
                await blacklist_token(f"family:{family}", ttl)
            raise TokenRevoked()

        if family:
            family_key = f"family:{family}"
            from src.core.redis import redis_client

            existing_family = await redis_client.get(family_key)
            if existing_family:
                ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
                await blacklist_token(f"family:{family}", ttl)
                raise TokenRevoked()
            await redis_client.setex(family_key, settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, jti or "")

        user_id = payload.get("sub")
        user = await self.user_repo.get(int(user_id))
        if not user:
            raise UserNotFound()

        ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
        if jti:
            await blacklist_token(jti, ttl)

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        new_refresh_token = create_refresh_token({"sub": str(user.id)}, family=family)

        return access_token, new_refresh_token

    async def logout(self, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token)
            jti = payload.get("jti")
            if jti:
                ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
                await blacklist_token(jti, ttl)
        except Exception:
            pass

    async def get_me(self, user_id: int) -> User:
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        return user
