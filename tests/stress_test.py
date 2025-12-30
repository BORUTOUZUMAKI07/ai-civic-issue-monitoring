import concurrent.futures
import requests
import time
import io
from PIL import Image

# Configuration
API_URL = "http://localhost:8000"
API_TOKEN = "secret-token" # Default from settings
NUM_REQUESTS = 50
CONCURRENT_WORKERS = 10

def create_test_image():
    """Create a 1x1 black JPEG image in memory."""
    buf = io.BytesIO()
    image = Image.new('RGB', (1, 1), color='black')
    image.save(buf, format='JPEG')
    buf.seek(0)
    return buf

def send_request(i):
    """Sends a single upload-issue request and returns elapsed time."""
    image_buf = create_test_image()
    files = {"file": ("stress_test.jpg", image_buf, "image/jpeg")}
    data = {"latitude": "22.3072", "longitude": "73.1812"}
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    
    start_time = time.time()
    try:
        response = requests.post(f"{API_URL}/upload-issue", headers=headers, files=files, data=data)
        elapsed = time.time() - start_time
        return i, response.status_code, elapsed
    except Exception as e:
        return i, str(e), time.time() - start_time

def run_stress_test():
    print(f"🚀 Starting Stress Test: {NUM_REQUESTS} requests with {CONCURRENT_WORKERS} workers...")
    
    results = []
    start_total = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
        futures = [executor.submit(send_request, i) for i in range(NUM_REQUESTS)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    
    end_total = time.time()
    total_duration = end_total - start_total
    
    # Calculate statistics
    success_count = sum(1 for r in results if r[1] == 200)
    latencies = [r[2] for r in results if isinstance(r[1], int) and r[1] == 200]
    
    print("\n--- Stress Test Results ---")
    print(f"Total Requests: {NUM_REQUESTS}")
    print(f"Successful: {success_count}")
    print(f"Failed: {NUM_REQUESTS - success_count}")
    print(f"Total Duration: {total_duration:.2f}s")
    print(f"Throughput: {success_count / total_duration:.2f} req/s")
    
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        print(f"Average Latency: {avg_latency:.2f}s")
        print(f"P95 Latency: {p95_latency:.2f}s")
    
    if success_count == NUM_REQUESTS:
        print("\n✅ System handled the load perfectly!")
    else:
        print("\n⚠️ Some requests failed or were throttled.")

if __name__ == "__main__":
    run_stress_test()
