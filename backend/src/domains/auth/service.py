from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from src.errors import EmailAlreadyExists, InvalidCredentials, InvalidToken, UserNotFound
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

    async def login(self, email: str, password: str) -> dict:
        user = await self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise InvalidCredentials()
        if not user.is_active:
            from src.errors import UnauthorizedError

            raise UnauthorizedError(detail="Account is deactivated.")

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    async def refresh(self, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise InvalidToken()

        if payload.get("type") != "refresh":
            raise InvalidToken()

        user_id = payload.get("sub")
        user = await self.user_repo.get(int(user_id))
        if not user:
            raise UserNotFound()

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        new_refresh_token = create_refresh_token({"sub": str(user.id)})

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        }

    async def get_me(self, user_id: int) -> User:
        user = await self.user_repo.get(user_id)
        if not user:
            raise UserNotFound()
        return user
