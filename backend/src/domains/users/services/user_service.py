"""Application use-cases for user administration.

These used to live inline in ``domains/admin/api/routes.py``. Moving them here
keeps the router free of SQL and role-swap rules, and makes the rules callable
and testable without HTTP.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.assignments.repositories.assignment_repository import AssignmentRepository
from src.domains.assignments.repositories.ports import AssignmentRepositoryPort
from src.domains.engineers.models.engineer import Engineer
from src.domains.engineers.repositories.engineer_repository import EngineerRepository
from src.domains.engineers.repositories.ports import EngineerRepositoryPort
from src.domains.users.models.user import User, UserRole
from src.domains.users.repositories.ports import UserRepositoryPort
from src.domains.users.repositories.user_repository import UserRepository
from src.shared.errors import ForbiddenError, NotFoundError


class UserService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        user_repo: UserRepositoryPort | None = None,
        engineer_repo: EngineerRepositoryPort | None = None,
        assignment_repo: AssignmentRepositoryPort | None = None,
    ):
        self.db = db
        self.user_repo: UserRepositoryPort = user_repo or UserRepository(db)
        self.engineer_repo: EngineerRepositoryPort = engineer_repo or EngineerRepository(db)
        self.assignment_repo: AssignmentRepositoryPort = assignment_repo or AssignmentRepository(db)

    async def list_users(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        search: str = "",
        role: str | None = None,
    ) -> tuple[list[User], int]:
        users = await self.user_repo.list_filtered(skip=skip, limit=limit, search=search, role=role)
        total = await self.user_repo.count_filtered(search=search, role=role)
        return users, total

    async def change_role(self, actor: User, user_id: int, new_role_value: str) -> User:
        """Promote/demote ``user_id`` on behalf of ``actor``.

        A user holds ONE functional role at a time, so a role change is a
        *swap*: the engineer profile (the operational field-deployment record)
        is kept in sync — created on promotion to ``engineer`` and removed on
        leaving it (unless the engineer still has open work).

        Every failure raises ``403``/``404`` with the same message the endpoint
        previously produced, so no client-visible wording changes.
        """
        valid_roles = [r.value for r in UserRole]
        if new_role_value not in valid_roles:
            raise ForbiddenError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
        if user_id == actor.id:
            raise ForbiddenError("Cannot change your own role.")

        target = await self.user_repo.get(user_id)
        if not target:
            raise NotFoundError("User not found.")
        if target.role == UserRole.super_admin:
            raise ForbiddenError("Cannot change the super admin's role.")
        if new_role_value == "super_admin":
            raise ForbiddenError("Super admin can only be assigned directly in the database.")
        if new_role_value == "admin" and actor.role != UserRole.super_admin:
            raise ForbiddenError("Only the super admin can promote to admin.")

        new_role = UserRole(new_role_value)
        profile = await self.engineer_repo.get_by_user_id(target.id)

        if new_role == UserRole.engineer:
            if profile is None:
                profile = Engineer(
                    user_id=target.id,
                    ward_id=1,
                    specialization="general",
                    max_workload=10,
                )
                self.db.add(profile)
        elif profile is not None:
            active = await self.assignment_repo.count_active_for_engineer(profile.id)
            if active:
                raise ForbiddenError(
                    "This engineer still has active assignments. Resolve them before changing the role."
                )
            await self.db.delete(profile)

        target.role = new_role
        await self.db.commit()
        await self.db.refresh(target)
        return target
