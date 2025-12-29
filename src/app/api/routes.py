from fastapi import APIRouter, UploadFile, File, Form, Depends, BackgroundTasks
from PIL import Image
import io

from app.core.security import verify_token
from app.core.image_validation import validate_image
from app.models.issue import IssueResponse, HealthResponse

from app.services.issue_service import IssueService
from app.services.monitoring_service import MonitoringService

from app.core.wards import WARDS

router = APIRouter()

@router.get("/health", tags=["System"], response_model=HealthResponse)
def health_check():
    return {"status": "ok"}


@router.get("/wards", tags=["Administrative"])
def get_wards_list():
    return WARDS


@router.post("/upload-issue", tags=["Issues"], response_model=IssueResponse)
async def upload_issue(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    latitude: str = Form(...),
    longitude: str = Form(...),
    token: str = Depends(verify_token),
):
    # Cast to float manually to avoid Pydantic validation 400s if sent as string
    lat_val = float(latitude)
    lon_val = float(longitude)
    # Phase 4: Image security & validation
    validate_image(file)

    # Load image
    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes))

    # Phase 3 & 5: Process Issue via Service
    result = await IssueService.process_issue(image, lat_val, lon_val)

    # Phase 6: Real-time Drift Monitoring (Background Task)
    background_tasks.add_task(
        MonitoringService.record_prediction, 
        issue_type=result.issue_type, 
        confidence=result.confidence
    )

    return result
