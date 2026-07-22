import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.deps import get_current_active_user
from src.domains.issues.service import IssueService
from src.errors import NotFoundError
from src.models.user import User
from src.repositories.engineer_repository import EngineerRepository

router = APIRouter(prefix="/resolution", tags=["Resolution"])

UPLOAD_DIR = Path("uploads/resolutions")


@router.post("")
async def resolve_issue(
    issue_id: str = Form(...),
    file: UploadFile = File(...),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    content = await file.read()

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = (file.filename or "after.jpg").split(".")[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = UPLOAD_DIR / filename
    await asyncio.to_thread(filepath.write_bytes, content)
    after_image_url = f"/uploads/resolutions/{filename}"

    engineer_repo = EngineerRepository(db)
    engineer = await engineer_repo.get_by_user_id(user.id)
    if not engineer:
        raise NotFoundError(detail="Engineer profile not found for this user.")

    svc = IssueService(db)
    resolution = await svc.create_resolution(
        issue_id=int(issue_id),
        engineer_id=engineer.id,
        after_image_url=after_image_url,
        notes=notes,
    )

    return {
        "id": resolution.id,
        "issue_id": resolution.issue_id,
        "status": "resolved",
        "message": f"Issue {issue_id} resolved successfully.",
        "resolved_at": resolution.resolved_at.isoformat(),
    }
