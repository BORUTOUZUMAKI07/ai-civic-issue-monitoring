import pytest
from fastapi.testclient import TestClient
from PIL import Image
import io
import os
from unittest.mock import patch

from app.main import app
from app.core.config import settings

client = TestClient(app)

def create_test_image():
    """Create a 1x1 black JPEG image in memory."""
    buf = io.BytesIO()
    image = Image.new('RGB', (1, 1), color='black')
    image.save(buf, format='JPEG')
    buf.seek(0)
    return buf

@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {settings.API_TOKEN}"}

@patch("app.services.issue_service.predict_issue")
def test_upload_issue_success(mock_predict, auth_headers):
    # Mock prediction result
    mock_predict.return_value = {
        "label": "pothole",
        "confidence": 0.95
    }
    
    image_buf = create_test_image()
    files = {"file": ("test.jpg", image_buf, "image/jpeg")}
    data = {"latitude": "22.3072", "longitude": "73.1812"}
    
    response = client.post("/upload-issue", headers=auth_headers, files=files, data=data)
    
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["issue_type"] == "pothole"
    assert json_data["status"] == "Open"
    assert "Ward-6" in json_data["ward"]  # 22.3, 73.1 is roughly Ward 6 center/Akota area

def test_upload_issue_unauthorized():
    image_buf = create_test_image()
    files = {"file": ("test.jpg", image_buf, "image/jpeg")}
    data = {"latitude": "22.3", "longitude": "73.1"}
    
    response = client.post("/upload-issue", files=files, data=data) # No headers
    assert response.status_code == 401 # HTTPBearer returns 401 if no auth header

def test_resolve_issue_success(auth_headers):
    image_buf = create_test_image()
    files = {"file": ("resolve.jpg", image_buf, "image/jpeg")}
    data = {
        "issue_id": "VMC-1234",
        "engineer_notes": "Pothole fixed with asphalt."
    }
    
    response = client.post("/resolve-issue", headers=auth_headers, files=files, data=data)
    
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["issue_id"] == "VMC-1234"
    assert json_data["status"] == "Resolved"
    assert "Pothole fixed" in json_data["resolution_message"]

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
