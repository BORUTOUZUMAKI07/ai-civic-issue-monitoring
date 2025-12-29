import pytest
from app.services.monitoring_service import MonitoringService, DRIFT_DETECTED_CONFIDENCE, DRIFT_DETECTED_LABEL, DRIFT_P_VALUE_CONFIDENCE
from ml.monitoring.drift_detection import DriftDetector
import pandas as pd
import numpy as np

def test_monitoring_service_buffering():
    # 1. Reset Singleton for test
    MonitoringService._detector = DriftDetector(window_size=5)
    
    # 2. Add 4 predictions (Buffer not full)
    for _ in range(4):
        MonitoringService.record_prediction("pothole", 0.95)
    
    # Check that NO drift metric has been computed yet (default is 0 or None)
    # Note: accessing prometheus metric value is tricky in unit tests without a registry,
    # but we can check if _update_metrics was called.
    # For now, let's just ensure no crash.
    
    # 3. Add 5th prediction (Buffer full -> Trigger Check)
    # This should be a "Good" prediction, so no drift.
    MonitoringService.record_prediction("pothole", 0.95)
    
    # 4. Drastic Drift Injection
    # Add 5 "Garbage" predictions with low confidence
    print("Injecting Drift...")
    for _ in range(5):
        MonitoringService.record_prediction("garbage", 0.10)
        
    # By now, metrics should be updated.
    # In a real running app, we'd query /metrics.
    # Here, we can verify the gauge values manually if needed, 
    # or just trust that no exception was raised.
    
    val = DRIFT_DETECTED_CONFIDENCE.collect()[0].samples[0].value
    print(f"Drift Detected Gauge Value: {val}")
    
    assert val == 1.0, "Drift should remain detected after bad batch"

if __name__ == "__main__":
    test_monitoring_service_buffering()
