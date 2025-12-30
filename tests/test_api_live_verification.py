import requests
import io
import pytest
from PIL import Image

API_URL = "http://localhost:8000"
API_TOKEN = "secret-token"

def create_test_image():
    buf = io.BytesIO()
    image = Image.new('RGB', (1, 1), color='black')
    image.save(buf, format='JPEG')
    buf.seek(0)
    return buf

@pytest.mark.skip(reason="Requires running server on localhost:8000")
def test_live_upload():
    print(f"📡 Testing Live Upload to {API_URL}...")
    image_buf = create_test_image()
    files = {"file": ("live_test.jpg", image_buf, "image/jpeg")}
    data = {"latitude": "22.3072", "longitude": "73.1812"}
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    
    response = requests.post(f"{API_URL}/upload-issue", headers=headers, files=files, data=data)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("✅ Live Upload Success!")
        print(f"Response: {response.json()}")
    else:
        print(f"❌ Live Upload Failed: {response.text}")

@pytest.mark.skip(reason="Requires running server on localhost:8000")
def test_live_resolve():
    print(f"\n📡 Testing Live Resolution to {API_URL}...")
    image_buf = create_test_image()
    files = {"file": ("resolve_test.jpg", image_buf, "image/jpeg")}
    data = {"issue_id": "TEST-123", "engineer_notes": "Live test resolution"}
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    
    response = requests.post(f"{API_URL}/resolve-issue", headers=headers, files=files, data=data)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("✅ Live Resolution Success!")
        print(f"Response: {response.json()}")
    else:
        print(f"❌ Live Resolution Failed: {response.text}")


