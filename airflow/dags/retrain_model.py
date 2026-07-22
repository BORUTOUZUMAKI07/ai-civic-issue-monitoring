"""
CivicPulse Model Retraining DAG
Runs weekly (Sunday 3 AM) to retrain the image classifier if drift is detected.
Pipeline: check_drift -> (if high) train_model -> evaluate -> register
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.mongo.hooks.mongo import MongoHook

logger = logging.getLogger(__name__)

default_args = {
    "owner": "civicpulse",
    "depends_on_past": False,
    "email_on_failure": True,
    "email": ["admin@civicpulse.com"],
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}


def check_drift_status(**context):
    """Check latest drift report to decide if retraining is needed."""
    hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = hook.get_conn()
    db = client["civicpulse_analytics"]

    latest = db["drift_reports"].find_one(
        sort=[("timestamp", -1)],
    )

    if not latest:
        logger.info("No drift reports found, skipping retrain")
        context["ti"].xcom_push(key="should_retrain", value=False)
        return "log_skip"

    severity = latest.get("severity", "low")
    drift_detected = latest.get("drift_detected", False)
    should_retrain = drift_detected and severity == "high"

    context["ti"].xcom_push(key="should_retrain", value=should_retrain)
    context["ti"].xcom_push(key="drift_report", value=latest)

    if should_retrain:
        logger.warning(
            "HIGH drift detected (mean_drift: %s%%), triggering retrain",
            latest.get("mean_drift_pct"),
        )
        return "train_model"
    else:
        logger.info("Drift severity: %s, no retrain needed", severity)
        return "log_skip"


def train_model(**context):
    """Run the MobileNetV2 training pipeline."""
    train_script = Path(__file__).resolve().parents[2] / "backend" / "ml" / "training" / "train.py"
    model_dir = Path(__file__).resolve().parents[2] / "backend" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = model_dir / f"model_retrained_{timestamp}.pth"

    cmd = [
        sys.executable,
        str(train_script),
        "--data-dir", "data/training",
        "--output", str(output_path),
        "--epochs", "20",
        "--batch-size", "32",
    ]

    logger.info("Running training: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        logger.error("Training failed:\n%s", result.stderr)
        raise RuntimeError(f"Training failed with exit code {result.returncode}")

    logger.info("Training output:\n%s", result.stdout[-2000:])

    metrics_path = output_path.with_suffix(".metrics.json")
    metrics = {}
    if metrics_path.exists():
        with open(metrics_path) as f:
            metrics = json.load(f)

    context["ti"].xcom_push(key="model_path", value=str(output_path))
    context["ti"].xcom_push(key="train_metrics", value=metrics)
    return metrics


def evaluate_and_register(**context):
    """Compare new model with current and register if better."""
    model_path = context["ti"].xcom_pull(key="model_path", task_ids="train_model")
    new_metrics = context["ti"].xcom_pull(key="train_metrics", task_ids="train_model")
    drift_report = context["ti"].xcom_pull(key="drift_report", task_ids="check_drift_status")

    hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = hook.get_conn()
    db = client["civicpulse_analytics"]

    new_acc = new_metrics.get("best_val_acc", 0)

    previous_reports = list(
        db["retrain_logs"].find().sort("timestamp", -1).limit(1)
    )
    prev_acc = previous_reports[0].get("new_val_acc", 0) if previous_reports else 0

    registered = new_acc > prev_acc or prev_acc == 0

    if registered:
        best_model_dir = Path(__file__).resolve().parents[2] / "backend" / "models"
        best_model = best_model_dir / "model_phase1.pth"
        import shutil
        shutil.copy2(model_path, best_model)
        logger.info("New model registered (acc: %.4f > prev: %.4f)", new_acc, prev_acc)
    else:
        logger.info("New model NOT better (acc: %.4f <= prev: %.4f), skipping", new_acc, prev_acc)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_path": model_path,
        "new_val_acc": round(new_acc, 4),
        "previous_val_acc": round(prev_acc, 4),
        "registered": registered,
        "drift_severity": drift_report.get("severity") if drift_report else "unknown",
        "drift_mean_pct": drift_report.get("mean_drift_pct") if drift_report else 0,
        "epochs": new_metrics.get("epochs", 0),
    }

    db["retrain_logs"].insert_one(log_entry)
    context["ti"].xcom_push(key="retrain_log", value=log_entry)
    logger.info("Retrain log: %s", json.dumps(log_entry, indent=2, default=str))


def log_skip(**context):
    """Log that retraining was skipped."""
    drift_report = context["ti"].xcom_pull(key="drift_report", task_ids="check_drift_status")

    hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = hook.get_conn()
    db = client["civicpulse_analytics"]

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "skipped",
        "reason": "no_high_drift",
        "drift_severity": drift_report.get("severity") if drift_report else "none",
    }

    db["retrain_logs"].insert_one(log_entry)
    logger.info("Retrain skipped: %s", json.dumps(log_entry))


with DAG(
    dag_id="retrain_model",
    default_args=default_args,
    description="Weekly ML model retraining triggered by drift detection",
    schedule_interval="0 3 * * 0",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["civicpulse", "ml", "retraining"],
) as dag:
    check = BranchPythonOperator(
        task_id="check_drift_status",
        python_callable=check_drift_status,
    )

    train = PythonOperator(
        task_id="train_model",
        python_callable=train_model,
    )

    evaluate = PythonOperator(
        task_id="evaluate_and_register",
        python_callable=evaluate_and_register,
    )

    skip_log = PythonOperator(
        task_id="log_skip",
        python_callable=log_skip,
    )

    check >> [train, skip_log]
    train >> evaluate
