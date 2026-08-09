"""Drift detection flow: fetch recent predictions, write a drift report.

Port of airflow/dags/drift_detection.py. Original schedule: daily 02:00 UTC.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from prefect import flow, get_run_logger, task

from connections import get_mongo_uri

MONGO_DB = "civicpulse_analytics"
BASELINE_MEAN = 0.75
BASELINE_STD = 0.15


@task(retries=1, retry_delay_seconds=300)
def fetch_recent_predictions(uri: str, days: int = 7) -> list[dict]:
    from pymongo import MongoClient

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with MongoClient(uri) as client:
        docs = list(
            client[MONGO_DB]["predictions"].find(
                {"created_at": {"$gte": cutoff}},
                {"_id": 0, "predicted_label": 1, "confidence": 1, "actual_label": 1},
            )
        )
    return docs


@task
def detect_drift(uri: str, predictions: list[dict]) -> dict | None:
    logger = get_run_logger()

    if not predictions:
        logger.info("No predictions found, skipping drift detection")
        return None

    confidences = [p["confidence"] for p in predictions if p.get("confidence") is not None]
    if len(confidences) < 10:
        logger.info("Not enough data for drift detection (%d samples)", len(confidences))
        return None

    mean_conf = statistics.mean(confidences)
    std_conf = statistics.pstdev(confidences)

    mean_drift = abs(mean_conf - BASELINE_MEAN) / BASELINE_MEAN
    std_drift = abs(std_conf - BASELINE_STD) / BASELINE_STD

    drift_detected = mean_drift > 0.15 or std_drift > 0.25
    severity = (
        "high"
        if mean_drift > 0.3 or std_drift > 0.5
        else "medium"
        if drift_detected
        else "low"
    )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(confidences),
        "mean_confidence": round(mean_conf, 4),
        "std_confidence": round(std_conf, 4),
        "mean_drift_pct": round(mean_drift * 100, 2),
        "std_drift_pct": round(std_drift * 100, 2),
        "drift_detected": drift_detected,
        "severity": severity,
    }

    with MongoClient(uri) as client:
        client[MONGO_DB]["drift_reports"].insert_one(report)

    if drift_detected and severity == "high":
        logger.warning(
            "HIGH drift detected! Mean: %.2f%%, Std: %.2f%%",
            mean_drift * 100,
            std_drift * 100,
        )
    logger.info("Drift report: %s", report)
    return report


@flow(
    name="drift-detection",
    description="Detect ML model performance drift",
    log_prints=True,
)
def drift_detection_flow() -> dict | None:
    uri = get_mongo_uri()
    predictions = fetch_recent_predictions(uri)
    return detect_drift(uri, predictions)
