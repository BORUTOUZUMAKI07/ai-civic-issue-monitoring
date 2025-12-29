from typing import Any, Dict, Deque, Optional
import pandas as pd
import numpy as np
from loguru import logger
import json
from pathlib import Path
from collections import deque

try:
    from alibi_detect.cd import KSDrift, ChiSquareDrift
    ALIBI_AVAILABLE = True
except ImportError:
    ALIBI_AVAILABLE = False
    logger.warning("⚠️ Alibi Detect not installed. Install with: uv sync --extra research")

# Import PROJECT_ROOT
try:
    from common.paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

class DriftDetector:
    def __init__(self, reference_data: pd.DataFrame = None, window_size: int = 5):
        """
        Initialize Drift Detector.
        
        Args:
            reference_data: DataFrame containing the baseline/training data.
            window_size: Number of recent samples to check for drift (Small for Hackathon demo!)
        """
        if not ALIBI_AVAILABLE:
            logger.error("Alibi Detect is required for Drift Monitoring.")
            return

        self.window_size = window_size
        self.prediction_buffer: Deque[Dict[str, Any]] = deque(maxlen=window_size)
        self.detectors: Dict[str, Any] = {}
        
        # Load reference data if not provided (Try to load from a default path or generate dummy)
        if reference_data is None:
             self.reference_data = self._load_default_reference()
        else:
             self.reference_data = reference_data

        if self.reference_data is not None:
            self._build_detectors()

    def _load_default_reference(self):
        """Hackathon Helper: Generate or load dummy reference data if none exists."""
        # For a real app, load from 'data/reference.csv'
        # For hackathon: generate 'perfect' data
        logger.info("Generating baseline reference data...")
        return pd.DataFrame({
            "issue_type": ["pothole"] * 50 + ["garbage"] * 30 + ["debris"] * 20,
            "confidence": np.random.normal(0.9, 0.05, 100)
        })

    def _build_detectors(self):
        """Builds drift detectors."""
        logger.info(f"Initializing Drift Detectors (Reference size: {len(self.reference_data)})")
        
        # 1. Label Drift (Categorical)
        if 'issue_type' in self.reference_data.columns:
            self.detectors['label_drift'] = ChiSquareDrift(
                x_ref=self.reference_data['issue_type'].values,
                p_val=0.05
            )
        
        # 2. Confidence Drift (Numerical)
        if 'confidence' in self.reference_data.columns:
            self.detectors['confidence_drift'] = KSDrift(
                x_ref=self.reference_data['confidence'].values,
                p_val=0.05
            )

    def add_prediction(self, issue_type: str, confidence: float):
        """Add a single prediction to buffer and check for drift if buffer is full."""
        self.prediction_buffer.append({
            "issue_type": issue_type,
            "confidence": confidence
        })
        
        if len(self.prediction_buffer) >= self.window_size:
            return self.check_drift()
        return None

    def check_drift(self) -> dict:
        """Run drift detection on the current buffer."""
        if not self.detectors:
            return {}
            
        current_data = pd.DataFrame(list(self.prediction_buffer))
        results = {}
        
        try:
            # 1. Label Drift
            if 'label_drift' in self.detectors:
                preds = self.detectors['label_drift'].predict(
                    current_data['issue_type'].values, 
                    return_p_val=True, 
                    return_distance=True
                )
                results['label_drift'] = self._format_result(preds, "issue_type")
                
            # 2. Confidence Drift
            if 'confidence_drift' in self.detectors:
                preds = self.detectors['confidence_drift'].predict(
                    current_data['confidence'].values,
                    return_p_val=True,
                    return_distance=True
                )
                results['confidence_drift'] = self._format_result(preds, "confidence")
                
        except Exception as e:
            logger.error(f"Drift check failed: {e}")
            
        return results

    def _format_result(self, raw_pred, feature_name):
        is_drift = bool(raw_pred['data']['is_drift'])
        p_val = float(raw_pred['data']['p_val'][0]) if isinstance(raw_pred['data']['p_val'], (list, np.ndarray)) else float(raw_pred['data']['p_val'])
        
        return {
            "is_drift": is_drift,
            "p_value": p_val
        }

if __name__ == "__main__":
    # Demo for Hackathon
    detector = DriftDetector(window_size=5)
    
    print("--- Simulating 5 bad predictions ---")
    for _ in range(5):
        # Simulate BAD data (Low confidence, wrong class)
        res = detector.add_prediction("garbage", 0.55) 
        if res:
            print(f"Drift Result: {json.dumps(res, indent=2)}")
