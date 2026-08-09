"""Model retraining — single dispatch flow (weekly trigger + event-driven check).

Event-driven redesign to fit Prefect's 500 serverless min/mo budget AND the
Hobby 5-deployment limit (retrain, drift, report, sla, archival):

- One deployment "retrain-model" with a `mode` parameter:
    mode="trigger" (weekly cron): check drift, if HIGH push empty commit,
    write retrain_state flag, emit "civicpulse.retrain.triggered", then end (~1 min).
    mode="check" (fired by automation or self-reschedule): poll MLflow once;
    if not finished, re-schedule itself in 5 min (self-rescheduling) up to 2h.
    Each poll ~20s. Zero cost when idle.
- An Automation listens for "civicpulse.retrain.triggered" and launches a
  mode="check" run. Check runs never emit that event, so no loop.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from prefect import flow, get_run_logger, task
from prefect.events import emit_event

from connections import (
    DAGSHUB_REPO,
    DAGSHUB_USER,
    MLFLOW_BASE,
    get_dagshub_token,
    get_mongo_uri,
)

DAGSHUB_GIT_URL = f"https://dagshub.com/{DAGSHUB_REPO}.git"
MLFLOW_EXPERIMENT = "civicpulse-peft-lora"
MLFLOW_RUN_NAME = "final-peft-model"
REGISTERED_MODEL = "civicpulse-mobilenetv2"
MONGO_DB = "civicpulse_analytics"
STATE_COLLECTION = "retrain_state"


# ---------- Shared helpers ----------

def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(cwd),
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed with exit code {result.returncode}: {result.stderr[-2000:]}")
    return result


# ---------- Trigger flow (weekly, scheduled) ----------

@task
def check_drift_status(uri: str) -> dict | None:
    logger = get_run_logger()
    from pymongo import MongoClient

    with MongoClient(uri) as client:
        latest = client[MONGO_DB]["drift_reports"].find_one(sort=[("timestamp", -1)])

    if not latest:
        logger.info("No drift reports found, skipping retrain")
        return None
    logger.info(
        "Latest drift report severity: %s, drift_detected: %s",
        latest.get("severity"),
        latest.get("drift_detected"),
    )
    return latest


@task(retries=1, retry_delay_seconds=600)
def trigger_retraining(token: str) -> int:
    logger = get_run_logger()

    home = Path(os.environ.get("HOME", "/tmp"))
    netrc = home / ".netrc"
    netrc.write_text(f"machine dagshub.com\n  login {DAGSHUB_USER}\n  password {token}\n")
    os.chmod(netrc, 0o600)

    work_dir = Path(tempfile.mkdtemp(prefix="civicpulse-retrain-"))
    _run_git(["clone", "--depth", "1", DAGSHUB_GIT_URL, str(work_dir)], work_dir.parent)
    _run_git(["config", "user.email", "civicpulse-airflow@civicpulse.com"], work_dir)
    _run_git(["config", "user.name", "CivicPulse Airflow"], work_dir)

    trigger_time_ms = int(time.time() * 1000)
    _run_git(
        ["commit", "--allow-empty", "-m", f"Airflow retrain trigger [{trigger_time_ms}]"],
        work_dir,
    )
    _run_git(["push", "origin", "main"], work_dir)
    shutil.rmtree(work_dir, ignore_errors=True)

    logger.info("Pushed empty commit; training workflow should start (ts=%s)", trigger_time_ms)
    return trigger_time_ms


@task
def write_retrain_state(uri: str, trigger_time_ms: int, drift_report: dict) -> None:
    logger = get_run_logger()
    from pymongo import MongoClient

    state_doc = {
        "in_progress": True,
        "trigger_time_ms": trigger_time_ms,
        "drift_severity": drift_report.get("severity"),
        "drift_mean_pct": drift_report.get("mean_drift_pct"),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    with MongoClient(uri) as client:
        client[MONGO_DB][STATE_COLLECTION].update_one(
            {"_id": "current"},
            {"$set": state_doc},
            upsert=True,
        )
    logger.info("Wrote retrain_state: in_progress=true, trigger_time_ms=%s", trigger_time_ms)


@task
def log_skip(uri: str, drift_report: dict | None) -> None:
    logger = get_run_logger()
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "skipped",
        "reason": "no_high_drift",
        "drift_severity": drift_report.get("severity") if drift_report else "none",
    }
    from pymongo import MongoClient
    with MongoClient(uri) as client:
        client[MONGO_DB]["retrain_logs"].insert_one(log_entry)
    logger.info("Retrain skipped: %s", json.dumps(log_entry))


@flow(
    name="retrain-model",
    description="Weekly ML retraining trigger + event-driven MLflow poller (self-rescheduling)",
    log_prints=True,
)
def retrain_model_flow(
    mode: str = "trigger",
    trigger_time_ms: int | None = None,
    drift_report: dict | None = None,
) -> dict:
    """Dispatch: mode="trigger" (weekly cron) or mode="check" (automation / self-reschedule)."""
    logger = get_run_logger()
    if mode == "check":
        return run_check(trigger_time_ms, drift_report)
    return run_trigger()


@task
def run_trigger() -> dict:
    """Weekly trigger: check drift → if HIGH, push commit, record state, emit event."""
    logger = get_run_logger()
    uri = get_mongo_uri()
    token = get_dagshub_token()

    drift_report = check_drift_status(uri)
    if (
        drift_report
        and drift_report.get("drift_detected")
        and drift_report.get("severity") == "high"
    ):
        trigger_time_ms = trigger_retraining(token)
        write_retrain_state(uri, trigger_time_ms, drift_report)
        emit_event(
            event="civicpulse.retrain.triggered",
            resource={
                "prefect.resource.id": "civicpulse.retrain",
                "prefect.resource.name": "retrain-model",
            },
            payload={"trigger_time_ms": trigger_time_ms},
        )
        return {"retrained": True, "trigger_time_ms": trigger_time_ms}

    log_skip(uri, drift_report)
    return {"retrained": False}


# ---------- Check logic (event-driven, self-rescheduling) ----------

@task(timeout_seconds=300)
def poll_training_status(token: str, trigger_time_ms: int) -> dict:
    """Single poll of DagsHub MLflow. Returns status dict."""
    logger = get_run_logger()
    auth = (DAGSHUB_USER, token)
    base = MLFLOW_BASE

    exp_resp = requests.get(f"{base}/experiments/list", auth=auth, timeout=30)
    exp_resp.raise_for_status()
    exp_id = next(
        e["experiment_id"]
        for e in exp_resp.json()["experiments"]
        if e["name"] == MLFLOW_EXPERIMENT
    )

    resp = requests.post(
        f"{base}/runs/search",
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
            values = run["data"].get("metrics", {}).get("best_val_acc", [])
            new_acc = float(values[-1]["value"]) if values else 0.0
            result = {
                "run_id": info["run_id"],
                "best_val_acc": new_acc,
                "best_params": run["data"].get("params", {}),
                "finished": True,
            }
            logger.info(
                "Training FINISHED run=%s best_val_acc=%.4f",
                info["run_id"],
                new_acc,
            )
            return result
        elif status in ("FAILED", "KILLED"):
            raise RuntimeError(
                f"Remote training run {info['run_id']} ended with status {status}"
            )

    # Still running
    return {"finished": False}


@task
def evaluate_and_register(uri: str, token: str, run_info: dict, drift_report: dict | None) -> None:
    logger = get_run_logger()
    auth = (DAGSHUB_USER, token)
    headers = {"Content-Type": "application/json"}
    new_run_id = run_info["run_id"]
    new_acc = run_info["best_val_acc"]
    best_params = run_info["best_params"]

    from pymongo import MongoClient

    with MongoClient(uri) as client:
        db = client[MONGO_DB]
        previous = list(db["retrain_logs"].find().sort("timestamp", -1).limit(1))
        prev_acc = previous[0].get("new_val_acc", 0) if previous else 0

    registered = new_acc > prev_acc or prev_acc == 0
    version = None

    if registered:
        create_resp = requests.post(
            f"{MLFLOW_BASE}/registered-models/create",
            auth=auth,
            headers=headers,
            json={"name": REGISTERED_MODEL},
            timeout=30,
        )
        if create_resp.status_code not in (200, 400):
            create_resp.raise_for_status()

        version_resp = requests.post(
            f"{MLFLOW_BASE}/registered-models/versions/create",
            auth=auth,
            headers=headers,
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
                f"{MLFLOW_BASE}/registered-models/versions/transition",
                auth=auth,
                headers=headers,
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
                REGISTERED_MODEL,
                version,
                new_acc,
                prev_acc,
            )
        else:
            logger.warning(
                "Model version creation failed (non-fatal): %s",
                version_resp.text[:500],
            )
    else:
        logger.info(
            "New model NOT better (acc: %.4f <= prev: %.4f), skipping",
            new_acc,
            prev_acc,
        )

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
    with MongoClient(uri) as client:
        client[MONGO_DB]["retrain_logs"].insert_one(log_entry)
    logger.info("Retrain log: %s", json.dumps(log_entry, indent=2, default=str))


@task
def clear_retrain_state(uri: str) -> None:
    logger = get_run_logger()
    from pymongo import MongoClient
    with MongoClient(uri) as client:
        client[MONGO_DB][STATE_COLLECTION].update_one(
            {"_id": "current"},
            {"$set": {"in_progress": False}},
        )
    logger.info("Cleared retrain_state")


@task
def run_check(
    trigger_time_ms: int | None = None,
    drift_report: dict | None = None,
) -> dict:
    """
    Event-driven polling logic (mode="check").
    - If trigger_time_ms/drift_report not passed, reads from retrain_state in Mongo.
    - Polls MLflow once; if not finished, re-schedules a check run in 5 min.
    - On FINISHED, evaluates and clears state.
    """
    logger = get_run_logger()
    uri = get_mongo_uri()
    token = get_dagshub_token()

    # If not called by automation with parameters, read from state
    if trigger_time_ms is None:
        from pymongo import MongoClient
        with MongoClient(uri) as client:
            state = client[MONGO_DB][STATE_COLLECTION].find_one({"_id": "current"})
        if not state or not state.get("in_progress"):
            logger.info("No active retrain in progress, exiting")
            return {"status": "no_active_retrain"}
        trigger_time_ms = state["trigger_time_ms"]
        # drift_report may not be in state; fetch latest as fallback
        if drift_report is None:
            drift_report = client[MONGO_DB]["drift_reports"].find_one(sort=[("timestamp", -1)])

    # Deadline guard: don't run past 2h from trigger
    deadline_ms = trigger_time_ms + 7_200_000  # 2h
    now_ms = int(time.time() * 1000)
    if now_ms > deadline_ms:
        logger.warning("Retrain deadline (2h) exceeded, giving up")
        clear_retrain_state(uri)
        return {"status": "deadline_exceeded"}

    poll_result = poll_training_status(token, trigger_time_ms)

    if poll_result.get("finished"):
        evaluate_and_register(uri, token, poll_result, drift_report)
        clear_retrain_state(uri)
        return {"status": "completed", **poll_result}

    # Not finished yet → re-schedule a check run in 5 minutes
    from datetime import timedelta
    from prefect.deployments import run_deployment

    logger.info("Training still running, scheduling next check in 5 min...")
    run_deployment(
        name="retrain-model/retrain-model",
        parameters={"mode": "check", "trigger_time_ms": trigger_time_ms, "drift_report": drift_report},
        scheduled_time=datetime.now(timezone.utc) + timedelta(minutes=5),
        timeout=0,
    )
    return {"status": "rescheduled"}