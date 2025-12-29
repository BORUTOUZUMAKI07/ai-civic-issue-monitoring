from prometheus_client import Gauge
from ml.monitoring.drift_detection import DriftDetector
from loguru import logger

# 1. Define Prometheus Metrics
DRIFT_P_VALUE_CONFIDENCE = Gauge(
    "model_drift_p_value_confidence", 
    "P-value for confidence drift (K-S Test)"
)
DRIFT_P_VALUE_LABEL = Gauge(
    "model_drift_p_value_label", 
    "P-value for label drift (Chi-Square Test)"
)
DRIFT_DETECTED_CONFIDENCE = Gauge(
    "model_drift_detected_confidence", 
    "1 if confidence drift detected, 0 otherwise"
)
DRIFT_DETECTED_LABEL = Gauge(
    "model_drift_detected_label", 
    "1 if label drift detected, 0 otherwise"
)

class MonitoringService:
    _detector = None

    @classmethod
    def get_detector(cls):
        """Lazy load detector to avoid startup delays."""
        if cls._detector is None:
            # Window size 5 for Hackathon (Visual responsiveness!)
            cls._detector = DriftDetector(window_size=5)
        return cls._detector

    @classmethod
    def record_prediction(cls, issue_type: str, confidence: float):
        """
        Record a prediction and update drift metrics if window is full.
        This runs in the background.
        """
        try:
            detector = cls.get_detector()
            drift_results = detector.add_prediction(issue_type, confidence)
            
            if drift_results:
                cls._update_metrics(drift_results)
                
        except Exception as e:
            logger.error(f"Error in MonitoringService: {e}")

    @staticmethod
    def _update_metrics(results: dict):
        """Update Prometheus Gauges."""
        logger.info(f"Parametheus Update: {results}")

        if "confidence_drift" in results:
            res = results["confidence_drift"]
            DRIFT_P_VALUE_CONFIDENCE.set(res["p_value"])
            DRIFT_DETECTED_CONFIDENCE.set(1 if res["is_drift"] else 0)

        if "label_drift" in results:
            res = results["label_drift"]
            DRIFT_P_VALUE_LABEL.set(res["p_value"])
            DRIFT_DETECTED_LABEL.set(1 if res["is_drift"] else 0)
