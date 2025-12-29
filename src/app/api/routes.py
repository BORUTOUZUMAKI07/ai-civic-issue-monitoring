from fastapi import APIRouter, UploadFile, File, Form, Depends, BackgroundTasks
from PIL import Image
import io
import uuid

from app.core.security import verify_token
from app.core.image_validation import validate_image
from app.models.issue import IssueResponse, HealthResponse, ResolutionResponse

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


@router.post("/resolve-issue", tags=["Issues"], response_model=ResolutionResponse)
async def resolve_issue(
    file: UploadFile = File(..., description="Resolution Image (After Photo)"),
    issue_id: str = Form(..., description="The Issue ID to resolve"),
    engineer_notes: str = Form("", description="Optional notes from the engineer"),
    token: str = Depends(verify_token),
):
    """
    Endpoint for VMC Engineers to upload resolution photos and close issues.
    
    Workflow:
    1. Engineer uploads "after" image showing the resolved state.
    2. System validates the image.
    3. Issue is marked as "Resolved".
    """
    # Validate image
    validate_image(file)
    
    # Read image (In production, you'd save this to storage)
    image_bytes = await file.read()
    _ = Image.open(io.BytesIO(image_bytes))  # Just validate it's a valid image
    
    # In production: Update database, send notifications, etc.
    # For Hackathon: Just return success response
    
    resolution_message = f"Issue {issue_id} has been successfully resolved."
    if engineer_notes:
        resolution_message += f" Engineer Notes: {engineer_notes}"
    
    return ResolutionResponse(
        issue_id=issue_id,
        status="Resolved",
        resolution_message=resolution_message,
        resolved_by="VMC Engineer (via API)"
    )
