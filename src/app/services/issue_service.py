from PIL import Image
from app.core.geofencing import get_ward
from app.core.routing import get_engineer_for_ward
from app.core.inference import predict_issue
from app.models.issue import IssueResponse
from loguru import logger

class IssueService:
    @staticmethod
    async def process_issue(image: Image.Image, latitude: float, longitude: float) -> IssueResponse:
        """
        Main business logic for processing a civic issue.
        """
        # 1. Run ML Inference
        prediction = predict_issue(image)
        label = prediction["label"]
        conf = prediction["confidence"]
        
        logger.info(f"ML Prediction: {label} ({conf})")

        # 2. Advanced Logic: Confidence & Severity
        review_required = False
        severity = 1
        
        # Rule A: Low Confidence Trigger
        if conf < 0.7:
            review_required = True
            logger.warning(f"Low confidence ({conf}) detected. Marking for manual review.")

        # Rule B: Severity Scoring (0-5)
        if label == "pothole":
            severity = 4 if conf > 0.8 else 3
        elif label == "garbage":
            severity = 3
        elif label == "debris":
            severity = 5 if conf > 0.8 else 3
        elif label == "non_civic":
            severity = 0
            review_required = False
            # Auto-close non-civic issues
        
        # 3. Geo-fencing
        ward = get_ward(latitude, longitude)
        logger.info(f"Issue located in: {ward}")

        # 4. Engineer Routing
        engineer = get_engineer_for_ward(ward)
        
        # Override for non-civic
        if label == "non_civic":
             status = "Rejected"
             message = "Issue rejected: Detected as Non-Civic (Not a pothole/garbage/debris)."
             assignee_email = "system.auto-reject@vmc.gov.in"
        else:
             status = "Pending Review" if review_required else "Open"
             message = f"Issue registered with severity {severity}. Assigned to {engineer['name']}"
             assignee_email = engineer["email"]

        logger.info(f"Final Status: {status}, Assigned: {assignee_email}")

        return IssueResponse(
            issue_type=label,
            confidence=conf,
            ward=ward,
            severity=severity,
            status=status,
            review_required=review_required,
            message=message,
            assigned_to=assignee_email,
            engineer_name=engineer["name"] if label != "non_civic" else "System",
            engineer_email=assignee_email
        )
