"""
CivicPulse ML Drift Detection DAG
Runs daily at 2 AM to detect model performance drift.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.mongo.hooks.mongo import MongoHook

logger = logging.getLogger(__name__)

default_args = {
    "owner": "civicpulse",
    "depends_on_past": False,
    "email_on_failure": True,
    "email": ["admin@civicpulse.com"],
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def fetch_recent_predictions(**context):
    """Fetch last 7 days of predictions from MongoDB."""
    hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = hook.get_conn()
    db = client["civicpulse_analytics"]
    collection = db["predictions"]

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    predictions = list(
        collection.find(
            {"created_at": {"$gte": seven_days_ago}},
            {"_id": 0, "predicted_label": 1, "confidence": 1, "actual_label": 1},
        )
    )
    context["ti"].xcom_push(key="predictions", value=predictions)
    logger.info("Fetched %d predictions from last 7 days", len(predictions))


def detect_drift(**context):
    """Detect distribution drift in predictions."""
    predictions = context["ti"].xcom_pull(key="predictions", task_ids="fetch_recent_predictions")

    if not predictions:
        logger.info("No predictions found, skipping drift detection")
        return

    confidences = [p.get("confidence", 0) for p in predictions if p.get("confidence") is not None]

    if len(confidences) < 10:
        logger.info("Not enough data for drift detection (%d samples)", len(confidences))
        return

    mean_conf = float(np.mean(confidences))
    std_conf = float(np.std(confidences))

    baseline_mean = 0.75
    baseline_std = 0.15

    mean_drift = abs(mean_conf - baseline_mean) / baseline_mean
    std_drift = abs(std_conf - baseline_std) / baseline_std

    drift_detected = mean_drift > 0.15 or std_drift > 0.25
    severity = "high" if mean_drift > 0.3 or std_drift > 0.5 else "medium" if drift_detected else "low"

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

    hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = hook.get_conn()
    db = client["civicpulse_analytics"]
    db["drift_reports"].insert_one(report)

    context["ti"].xcom_push(key="drift_report", value=report)
    logger.info("Drift report: %s", json.dumps(report, indent=2))

    if drift_detected and severity == "high":
        logger.warning("HIGH drift detected! Mean: %.2f%%, Std: %.2f%%", mean_drift * 100, std_drift * 100)


with DAG(
    dag_id="drift_detection",
    default_args=default_args,
    description="Detect ML model performance drift",
    schedule="0 2 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["civicpulse", "ml", "drift"],
) as dag:
    fetch = PythonOperator(
        task_id="fetch_recent_predictions",
        python_callable=fetch_recent_predictions,
    )

    detect = PythonOperator(
        task_id="detect_drift",
        python_callable=detect_drift,
    )

    fetch >> detect
