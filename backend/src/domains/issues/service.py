import io
from datetime import datetime, timedelta, timezone

import pillow_heif
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.wards.geofencing import get_ward_from_coords
from src.errors import CorruptedImageError, ImageTooLargeError, InvalidImageError, IssueNotFound
from src.models.assignment import Assignment, AssignmentStatus
from src.models.engineer import Engineer
from src.models.issue import ISSUE_TYPE_MAP, Issue, IssueStatus, IssueType
from src.models.resolution import Resolution
from src.repositories.assignment_repository import AssignmentRepository
from src.repositories.engineer_repository import EngineerRepository
from src.repositories.issue_repository import IssueRepository
from src.repositories.resolution_repository import ResolutionRepository
from src.repositories.user_repository import UserRepository
from src.repositories.ward_repository import WardRepository

pillow_heif.register_heif_opener()

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic"}
MAX_FILE_SIZE_MB = 5


class IssueService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.issue_repo = IssueRepository(db)
        self.ward_repo = WardRepository(db)
        self.engineer_repo = EngineerRepository(db)
        self.resolution_repo = ResolutionRepository(db)
        self.assignment_repo = AssignmentRepository(db)
        self.user_repo = UserRepository(db)

    def validate_image(self, filename: str, content: bytes) -> None:
        ext = filename.split(".")[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise InvalidImageError(f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise ImageTooLargeError()

        try:
            image = Image.open(io.BytesIO(content))
            image.verify()
        except Exception:
            raise CorruptedImageError()

    def read_image(self, content: bytes) -> Image.Image:
        """Open and fully decode an image into a PIL Image for ML inference."""
        try:
            return Image.open(io.BytesIO(content)).convert("RGB")
        except Exception as e:
            raise CorruptedImageError() from e

    async def create_issue(
        self,
        image_url: str,
        latitude: float,
        longitude: float,
        reporter_id: int,
        classification: dict,
        description: str = "",
    ) -> Issue:
        label = classification["label"]
        confidence = classification["confidence"]
        model_used = classification.get("model")
        probabilities = classification.get("probabilities")

        issue_type = ISSUE_TYPE_MAP.get(label, IssueType.pothole)

        severity = 1
        review_required = False
        if confidence < 0.7:
            review_required = True
        if label == "pothole":
            severity = 4 if confidence > 0.8 else 3
        elif label == "garbage":
            severity = 3
        elif label == "debris":
            severity = 5 if confidence > 0.8 else 3
        elif label in ("waterlogging", "sewage"):
            severity = 4 if confidence > 0.8 else 3
        elif label == "broken_streetlight":
            severity = 2
        elif label == "road_damage":
            severity = 4 if confidence > 0.8 else 3

        wards = await self.ward_repo.list_all()
        ward = get_ward_from_coords(latitude, longitude, wards)
        if not ward:
            ward = wards[0] if wards else None

        issue = Issue(
            issue_type=issue_type,
            confidence=confidence,
            severity=severity,
            status=IssueStatus.reported,
            latitude=latitude,
            longitude=longitude,
            description=description,
            image_url=image_url,
            review_required=review_required,
            model_used=model_used,
            probabilities=probabilities,
            ward_id=ward.id if ward else 1,
            reporter_id=reporter_id,
        )
        return await self.issue_repo.create(issue)

    async def assign_engineer(self, issue: Issue) -> Engineer | None:
        engineers = await self.engineer_repo.get_by_ward(issue.ward_id)
        if not engineers:
            return None

        engineer = min(engineers, key=lambda e: e.current_workload)
        if engineer.current_workload < engineer.max_workload:
            await self.engineer_repo.increment_workload(engineer.id)

            assignment = Assignment(
                issue_id=issue.id,
                engineer_id=engineer.id,
                status=AssignmentStatus.pending,
                sla_deadline=datetime.now(timezone.utc) + timedelta(hours=48),
            )
            await self.assignment_repo.create(assignment)

            issue.status = IssueStatus.assigned
            await self.issue_repo.commit()

            return engineer
        return None

    async def assign_issue_to_engineer(self, issue: Issue, engineer_id: int) -> Engineer:
        engineer = await self.engineer_repo.get(engineer_id)
        if not engineer:
            from src.errors import BadRequestError
            raise BadRequestError("Engineer not found.")
        if not engineer.is_available:
            from src.errors import BadRequestError
            raise BadRequestError("Engineer is not available.")
        if engineer.current_workload >= engineer.max_workload:
            from src.errors import BadRequestError
            raise BadRequestError("Engineer is at maximum workload.")

        existing = await self.assignment_repo.get_by_issue(issue.id)
        if existing:
            await self.engineer_repo.decrement_workload(existing.engineer_id)

        await self.engineer_repo.increment_workload(engineer.id)

        assignment = Assignment(
            issue_id=issue.id,
            engineer_id=engineer.id,
            status=AssignmentStatus.pending,
            sla_deadline=datetime.now(timezone.utc) + timedelta(hours=48),
        )
        await self.assignment_repo.create(assignment)

        issue.status = IssueStatus.assigned
        await self.issue_repo.commit()

        return engineer

    async def get_engineer_name(self, user_id: int) -> str | None:
        user = await self.user_repo.get(user_id)
        return user.full_name if user else None

    async def get_issue(self, issue_id: int) -> Issue:
        issue = await self.issue_repo.get(issue_id)
        if not issue:
            raise IssueNotFound()
        return issue

    async def list_issues(self, skip: int = 0, limit: int = 20) -> tuple[list[Issue], int]:
        issues = await self.issue_repo.list_all(skip=skip, limit=limit)
        total = await self.issue_repo.count()
        return issues, total

    async def list_issues_by_ward(self, ward_id: int, skip: int = 0, limit: int = 20) -> tuple[list[Issue], int]:
        issues = await self.issue_repo.list_by_ward(ward_id, skip=skip, limit=limit)
        total = await self.issue_repo.count()
        return issues, total

    async def update_status(self, issue_id: int, status: str) -> Issue:
        issue_status = IssueStatus(status)
        issue = await self.issue_repo.update_status(issue_id, issue_status)
        if not issue:
            raise IssueNotFound()
        return issue

    async def create_resolution(
        self,
        issue_id: int,
        engineer_id: int,
        after_image_url: str,
        notes: str = "",
    ) -> Resolution:
        issue = await self.get_issue(issue_id)
        resolution = Resolution(
            issue_id=issue_id,
            engineer_id=engineer_id,
            before_image_url=issue.image_url,
            after_image_url=after_image_url,
            notes=notes,
        )
        created = await self.resolution_repo.create(resolution)
        await self.issue_repo.update_status(issue_id, IssueStatus.resolved)
        return created

    async def get_dashboard_stats(self) -> dict:
        total = await self.issue_repo.count()
        by_status = await self.issue_repo.count_by_status()
        by_type = await self.issue_repo.count_by_type()
        by_ward = await self.issue_repo.count_by_ward()
        recent = await self.issue_repo.get_recent(days=30)

        return {
            "total_issues": total,
            "by_status": by_status,
            "by_type": by_type,
            "by_ward": by_ward,
            "recent_count": len(recent),
        }

    async def get_heatmap_data(self) -> list[dict]:
        return await self.issue_repo.get_heatmap_points()
