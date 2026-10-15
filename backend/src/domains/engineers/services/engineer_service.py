from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.assignments.repositories.assignment_repository import AssignmentRepository
from src.domains.engineers.models.engineer import Engineer
from src.domains.engineers.repositories.engineer_repository import EngineerRepository
from src.domains.users.models.user import UserRole
from src.domains.users.repositories.user_repository import UserRepository
from src.shared.errors import BadRequestError, NotFoundError


class EngineerService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.engineer_repo = EngineerRepository(db)
        self.user_repo = UserRepository(db)
        self.assignment_repo = AssignmentRepository(db)

    async def list_engineers(self):
        return await self.engineer_repo.list_all()

    async def get_engineer(self, engineer_id: int):
        return await self.engineer_repo.get(engineer_id)

    async def get_my_profile(self, user_id: int) -> Engineer:
        engineer = await self.engineer_repo.get_by_user_id(user_id)
        if not engineer:
            raise NotFoundError("Engineer profile not found for this user.")
        return engineer

    async def create_engineer(
        self,
        *,
        user_id: int,
        ward_id: int,
        specialization: str,
        max_workload: int,
    ) -> Engineer:
        """Explicitly make ``user_id`` an engineer.

        Swaps their role to ``engineer`` in one step and creates the profile.
        Rejects a duplicate profile, an unknown user, and the super admin.
        """
        if await self.engineer_repo.get_by_user_id(user_id):
            raise BadRequestError("This user already has an engineer profile.")

        target_user = await self.user_repo.get(user_id)
        if not target_user:
            raise NotFoundError("User not found.")
        if target_user.role == UserRole.super_admin:
            raise BadRequestError("Cannot give the super admin an engineer profile.")

        target_user.role = UserRole.engineer
        await self.db.commit()

        engineer = Engineer(
            user_id=user_id,
            ward_id=ward_id,
            specialization=specialization,
            max_workload=max_workload,
        )
        return await self.engineer_repo.create(engineer)

    async def list_my_assignments(self, user_id: int) -> list[dict[str, Any]]:
        engineer = await self.engineer_repo.get_by_user_id(user_id)
        if not engineer:
            raise BadRequestError("You do not have an engineer profile.")

        rows = await self.assignment_repo.list_by_engineer_with_issue(engineer.id)
        return [
            {
                "assignment_id": a.id,
                "status": a.status.value,
                "assigned_at": a.assigned_at.isoformat(),
                "sla_deadline": a.sla_deadline.isoformat(),
                "issue_id": i.id,
                "issue_type": i.issue_type.value,
                "severity": i.severity,
                "issue_status": i.status.value,
                "latitude": i.latitude,
                "longitude": i.longitude,
                "description": i.description,
                "image_url": i.image_url,
                "ward_id": i.ward_id,
                "created_at": i.created_at.isoformat(),
            }
            for a, i in rows
        ]
