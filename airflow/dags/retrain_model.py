"""
CivicPulse Model Retraining DAG
Runs weekly (Sunday 3 AM) to retrain the image classifier if drift is detected.

Pipeline: check_drift -> (if high) trigger_dagsHub_action -> poll_training -> evaluate_and_register
Trigger mechanism: DagsHub has no Actions dispatch API, so we push an empty commit
to `main`, which the "Train PEFT Classifier" workflow (.github/workflows/train.yml)
listens to via `on: push: branches: [main]`.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.mongo.hooks.mongo import MongoHook

logger = logging.getLogger(__name__)

DAGSHUB_REPO = "ram.atchutratna/ai-civic-issue-monitoring"
DAGSHUB_GIT_URL = f"https://dagshub.com/{DAGSHUB_REPO}.git"
MLFLOW_BASE = f"https://dagshub.com/{DAGSHUB_REPO}.mlflow/api/2.0/mlflow"
MLFLOW_EXPERIMENT = "civicpulse-peft-lora"
MLFLOW_RUN_NAME = "final-peft-model"
REGISTERED_MODEL = "civicpulse-mobilenetv2"
MONGO_DB = "civicpulse_analytics"

WORK_DIR = Path("/tmp/civicpulse-retrain")

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
    db = client[MONGO_DB]

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
        return "trigger_retraining"
    else:
        logger.info("Drift severity: %s, no retrain needed", severity)
        return "log_skip"


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a git command with DagsHub auth from .netrc, raising on failure."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(cwd),
    )
    if result.returncode != 0:
        logger.error("git %s failed:\n%s", args[0], result.stderr[-2000:])
        raise RuntimeError(f"git {args[0]} failed with exit code {result.returncode}")
    return result


def trigger_retraining(**context):
    """Push an empty commit to `main` to fire the DagsHub Actions training workflow."""
    token = Variable.get("DAGSHUB_TOKEN")

    netrc_dir = Path(os.environ.get("HOME", "/usr/local/airflow"))
    netrc_path = netrc_dir / ".netrc"
    netrc_path.write_text(
        f"machine dagshub.com\n  login ram.atchutratna\n  password {token}\n"
    )
    os.chmod(netrc_path, 0o600)

    if WORK_DIR.exists():
        import shutil
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True)

    _run_git(["clone", "--depth", "1", DAGSHUB_GIT_URL, str(WORK_DIR)], Path("/tmp"))
    _run_git(["config", "user.email", "civicpulse-airflow@civicpulse.com"], WORK_DIR)
    _run_git(["config", "user.name", "CivicPulse Airflow"], WORK_DIR)

    trigger_time_ms = int(time.time() * 1000)
    _run_git(
        ["commit", "--allow-empty", "-m", f"Airflow retrain trigger [{trigger_time_ms}]"],
        WORK_DIR,
    )
    _run_git(["push", "origin", "main"], WORK_DIR)

    context["ti"].xcom_push(key="trigger_time_ms", value=trigger_time_ms)
    logger.info("Pushed empty commit; training workflow should start (ts=%s)", trigger_time_ms)
    return trigger_time_ms


def poll_training_status(**context):
    """Poll DagsHub MLflow for the final training run to finish, then return its metrics."""
    trigger_time_ms = context["ti"].xcom_pull(
        key="trigger_time_ms", task_ids="trigger_retraining"
    )
    token = Variable.get("DAGSHUB_TOKEN")
    auth = ("ram.atchutratna", token)
    deadline = time.time() + 7200  # 2h cap

    exp_resp = requests.get(
        f"{MLFLOW_BASE}/experiments/search",
        params={"max_results": 100},
        auth=auth, timeout=30,
    )
    exp_resp.raise_for_status()
    exp_id = next(
        (e["experiment_id"] for e in exp_resp.json().get("experiments", []) if e["name"] == MLFLOW_EXPERIMENT),
        None,
    )
    if exp_id is None:
        raise RuntimeError(
            f"MLflow experiment {MLFLOW_EXPERIMENT!r} not found on DagsHub MLflow server"
        )

    while time.time() < deadline:
        resp = requests.post(
            f"{MLFLOW_BASE}/runs/search",
            auth=auth,
            json={
                "experiment_ids": [exp_id],
                "max_results": 20,
                "order_by": ["start_time DESC"],
            },
            timeout=30,
        )
        resp.raise_for_status()

        for run in resp.json().get("runs", []):
            info = run["info"]
            if info.get("run_name") != MLFLOW_RUN_NAME:
                continue
            if info.get("start_time", 0) < trigger_time_ms:
                continue

            status = info.get("status")
            if status == "FINISHED":
                metrics = {
                    m["key"]: m["value"]
                    for m in run["data"].get("metrics", {}).get("best_val_acc", [])
                }
                params = run["data"].get("params", {})
                new_acc = metrics.get("best_val_acc", 0.0)
                context["ti"].xcom_push(key="new_run_id", value=info["run_id"])
                context["ti"].xcom_push(key="new_val_acc", value=new_acc)
                context["ti"].xcom_push(key="train_metrics", value={"best_val_acc": new_acc})
                context["ti"].xcom_push(key="best_params", value=params)
                logger.info(
                    "Training FINISHED run=%s best_val_acc=%.4f",
                    info["run_id"], new_acc,
                )
                return {"run_id": info["run_id"], "best_val_acc": new_acc}
            elif status in ("FAILED", "KILLED"):
                raise RuntimeError(
                    f"Remote training run {info['run_id']} ended with status {status}"
                )

        logger.info("Training still running, polling again in 120s...")
        time.sleep(120)

    raise TimeoutError("Remote training did not finish within 2h")


def evaluate_and_register(**context):
    """Compare new model with current and register to MLflow Model Registry if better."""
    new_run_id = context["ti"].xcom_pull(key="new_run_id", task_ids="poll_training_status")
    new_acc = context["ti"].xcom_pull(key="new_val_acc", task_ids="poll_training_status")
    best_params = context["ti"].xcom_pull(key="best_params", task_ids="poll_training_status")
    drift_report = context["ti"].xcom_pull(key="drift_report", task_ids="check_drift_status")
    token = Variable.get("DAGSHUB_TOKEN")
    auth = ("ram.atchutratna", token)
    headers = {"Content-Type": "application/json"}

    hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = hook.get_conn()
    db = client[MONGO_DB]

    previous_reports = list(db["retrain_logs"].find().sort("timestamp", -1).limit(1))
    prev_acc = previous_reports[0].get("new_val_acc", 0) if previous_reports else 0

    registered = new_acc > prev_acc or prev_acc == 0

    version = None
    if registered:
        # Create registered model (ignore if already exists)
        create_resp = requests.post(
            f"{MLFLOW_BASE}/registered-models/create",
            auth=auth, headers=headers,
            json={"name": REGISTERED_MODEL},
            timeout=30,
        )
        if create_resp.status_code not in (200, 400):
            create_resp.raise_for_status()

        version_resp = requests.post(
            f"{MLFLOW_BASE}/model-versions/create",
            auth=auth, headers=headers,
            json={
                "name": REGISTERED_MODEL,
                "source": f"runs:/{new_run_id}/model",
                "run_id": new_run_id,
            },
            timeout=60,
        )
        if version_resp.status_code == 200:
            version = version_resp.json()["model_version"]["version"]
            transition_resp = requests.post(
                f"{MLFLOW_BASE}/model-versions/transition-stage",
                auth=auth, headers=headers,
                json={
                    "name": REGISTERED_MODEL,
                    "version": version,
                    "stage": "Staging",
                    "archive_existing_versions": True,
                },
                timeout=30,
            )
            if transition_resp.status_code != 200:
                logger.warning(
                    "Stage transition to Staging failed: %s",
                    transition_resp.text[:500],
                )
            logger.info(
                "Registered model %s v%s (acc: %.4f > prev: %.4f)",
                REGISTERED_MODEL, version, new_acc, prev_acc,
            )
        else:
            logger.warning(
                "Model version creation failed (non-fatal): %s", version_resp.text[:500]
            )
    else:
        logger.info("New model NOT better (acc: %.4f <= prev: %.4f), skipping", new_acc, prev_acc)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "dagshub_actions",
        "new_val_acc": round(new_acc, 4),
        "previous_val_acc": round(prev_acc, 4),
        "registered": registered,
        "registered_model": REGISTERED_MODEL,
        "model_version": version,
        "mlflow_run_id": new_run_id,
        "peft_method": best_params.get("peft_method", "unknown"),
        "best_params": best_params,
        "drift_severity": drift_report.get("severity") if drift_report else "unknown",
        "drift_mean_pct": drift_report.get("mean_drift_pct") if drift_report else 0,
    }

    db["retrain_logs"].insert_one(log_entry)
    context["ti"].xcom_push(key="retrain_log", value=log_entry)
    logger.info("Retrain log: %s", json.dumps(log_entry, indent=2, default=str))


def log_skip(**context):
    """Log that retraining was skipped."""
    drift_report = context["ti"].xcom_pull(key="drift_report", task_ids="check_drift_status")

    hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = hook.get_conn()
    db = client[MONGO_DB]

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
    schedule="0 3 * * 0",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["civicpulse", "ml", "retraining"],
) as dag:
    check = BranchPythonOperator(
        task_id="check_drift_status",
        python_callable=check_drift_status,
    )

    trigger = PythonOperator(
        task_id="trigger_retraining",
        python_callable=trigger_retraining,
    )

    poll = PythonOperator(
        task_id="poll_training_status",
        python_callable=poll_training_status,
        execution_timeout=timedelta(hours=3),
    )

    evaluate = PythonOperator(
        task_id="evaluate_and_register",
        python_callable=evaluate_and_register,
    )

    skip_log = PythonOperator(
        task_id="log_skip",
        python_callable=log_skip,
    )

    check >> [trigger, skip_log]
    trigger >> poll >> evaluate
