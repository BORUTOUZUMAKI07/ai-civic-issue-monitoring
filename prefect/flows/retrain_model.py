"""Model retraining — single dispatch flow (weekly trigger + event-driven check).

Event-driven redesign to fit Prefect's 500 serverless min/mo budget AND the
Hobby 5-deployment limit (retrain, drift, report, sla, archival):

- One deployment "retrain-model" with a `mode` parameter:
    mode="trigger" (weekly cron): check drift, if HIGH dispatch the GitHub
    Actions workflow via `repository_dispatch`, write retrain_state, emit
    "civicpulse.retrain.triggered", then end (~1 min).
    mode="check" (fired by automation or self-reschedule): poll MLflow once;
    if not finished, re-schedule itself in 5 min (self-rescheduling) up to 2h.
    Each poll ~20s. Zero cost when idle.
- An Automation listens for "civicpulse.retrain.triggered" and launches a
  mode="check" run. Check runs never emit that event, so no loop.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone

import requests
from prefect import flow, get_run_logger, task
from prefect.events import emit_event

from connections import (
    DAGSHUB_REPO,
    DAGSHUB_USER,
    GITHUB_REPOSITORY,
    MLFLOW_BASE,
    get_dagshub_token,
    get_github_token,
    get_mongo_uri,
)

DAGSHUB_USER = DAGSHUB_USER or os.getenv("DAGSHUB_USERNAME") or "ram.atchutratna"
DAGSHUB_REPO = DAGSHUB_REPO or os.getenv("DAGSHUB_REPO") or "ai-civic-issue-monitoring"
MLFLOW_EXPERIMENT = "civicpulse-peft-lora"
MLFLOW_RUN_NAME = "final-peft-model"
REGISTERED_MODEL = "civicpulse-mobilenetv2"
MONGO_DB = "civicpulse_analytics"
STATE_COLLECTION = "retrain_state"


# ---------- Shared helpers ----------

def dispatch_retrain(token: str, trigger_time_ms: int, repository: str | None = None) -> dict:
    """Start the GitHub Actions training workflow through repository_dispatch.

    The old flow pushed an empty commit to the DagsHub mirror. GitHub Actions
    only watches the GitHub remote, so no training ever started. A dispatch is
    explicit, needs no checkout and cannot race with ordinary source pushes.
    The PAT is used in a header only; it is never logged or stored in Mongo.
    """
    repo = repository or GITHUB_REPOSITORY
    response = requests.post(
        f"https://api.github.com/repos/{repo}/dispatches",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "event_type": "retrain-model",
            "client_payload": {"trigger_time_ms": trigger_time_ms, "source": "prefect"},
        },
        timeout=30,
    )
    response.raise_for_status()
    return {"status_code": response.status_code, "repository": repo}


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


@task(retries=2, retry_delay_seconds=60)
def trigger_retraining(token: str) -> int:
    logger = get_run_logger()
    trigger_time_ms = int(time.time() * 1000)
    dispatch = dispatch_retrain(token, trigger_time_ms)
    logger.info(
        "Dispatched GitHub retrain workflow (repo=%s, ts=%s, http=%s)",
        dispatch["repository"],
        trigger_time_ms,
        dispatch["status_code"],
    )
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
        client[MONGO_DB]["retrain_logs"].insert_one(dict(log_entry))
    logger.info("Retrain skipped: %s", json.dumps(log_entry))


@flow(
    name="retrain-model",
    description="Weekly ML retrain trigger + drift-triggered retrain + event-driven MLflow poller",
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
    """Weekly trigger: check drift → if HIGH, dispatch Actions, record state, emit event."""
    logger = get_run_logger()
    uri = get_mongo_uri()
    token = get_github_token()

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


# ---------- Registration gate (pure, unit-tested) ----------


def _accuracy(value: object) -> float | None:
    """Parse a metric value; missing/NaN/infinite values mean 'no metric'."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def extract_accuracy(run_data: dict) -> float | None:
    """Read best_val_acc from an MLflow run without inventing a 0.0 value."""
    for metric in run_data.get("metrics", []):
        if metric.get("key") == "best_val_acc":
            return _accuracy(metric.get("value"))
    return None


def should_register(new_acc: float | None, prev_acc: float | None) -> bool:
    """Only register a real, positive improvement.

    A missing metric used to default to 0.0 and ``prev_acc == 0`` forced
    registration, so a metric-less run could replace the serving model. A
    reported 0.0 is not a usable accuracy either.
    """
    if new_acc is None or not math.isfinite(new_acc) or new_acc <= 0.0:
        return False
    if prev_acc is None or not math.isfinite(prev_acc) or prev_acc <= 0.0:
        return True
    return new_acc > prev_acc


def _fmt_acc(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


# ---------- Check logic (event-driven, self-rescheduling) ----------

@task(timeout_seconds=300)
def poll_training_status(token: str, trigger_time_ms: int) -> dict:
    """Single poll of DagsHub MLflow. Returns status dict."""
    logger = get_run_logger()
    auth = (DAGSHUB_USER, token)
    base = MLFLOW_BASE

    exp_resp = requests.get(
        f"{base}/experiments/search",
        params={"max_results": 100},
        auth=auth,
        timeout=30,
    )
    exp_resp.raise_for_status()
    exp_id = next(
        (e["experiment_id"] for e in exp_resp.json().get("experiments", []) if e["name"] == MLFLOW_EXPERIMENT),
        None,
    )
    if exp_id is None:
        logger.warning(
            "MLflow experiment %r not found (server may have no runs yet)",
            MLFLOW_EXPERIMENT,
        )
        return {"finished": False, "status": "experiment_not_found"}

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
            new_acc = extract_accuracy(run.get("data", {}))
            params = run["data"].get("params", [])
            best_params = {p.get("key"): p.get("value") for p in params}
            result = {
                "run_id": info["run_id"],
                "best_val_acc": new_acc,
                "best_params": best_params,
                "finished": True,
            }
            logger.info(
                "Training FINISHED run=%s best_val_acc=%s",
                info["run_id"],
                _fmt_acc(new_acc),
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
    new_acc = _accuracy(run_info.get("best_val_acc"))
    best_params = run_info.get("best_params") or {}

    from pymongo import MongoClient

    with MongoClient(uri) as client:
        db = client[MONGO_DB]
        previous = list(db["retrain_logs"].find().sort("timestamp", -1).limit(1))
        prev_acc = _accuracy(previous[0].get("new_val_acc")) if previous else None

    registered = should_register(new_acc, prev_acc)
    reason = (
        "registered"
        if registered
        else ("missing_validation_metric" if new_acc is None else "not_better")
    )
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
            f"{MLFLOW_BASE}/model-versions/create",
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
                f"{MLFLOW_BASE}/model-versions/transition-stage",
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
                "Registered model %s v%s (acc: %s > prev: %s)",
                REGISTERED_MODEL,
                version,
                _fmt_acc(new_acc),
                _fmt_acc(prev_acc),
            )
        else:
            logger.warning(
                "Model version creation failed (non-fatal): %s",
                version_resp.text[:500],
            )
    else:
        logger.info(
            "New model NOT registered (reason: %s, acc: %s, prev: %s)",
            reason,
            _fmt_acc(new_acc),
            _fmt_acc(prev_acc),
        )

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "dagshub_actions",
        "new_val_acc": round(new_acc, 4) if new_acc is not None else None,
        "previous_val_acc": round(prev_acc, 4) if prev_acc is not None else None,
        "registration_reason": reason,
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
            # drift_report may not be in state; fetch latest as fallback
            if drift_report is None:
                drift_report = client[MONGO_DB]["drift_reports"].find_one(sort=[("timestamp", -1)])
                if drift_report is not None:
                    drift_report.pop("_id", None)  # ObjectId is not JSON-serializable
        if not state or not state.get("in_progress"):
            logger.info("No active retrain in progress, exiting")
            return {"status": "no_active_retrain"}
        trigger_time_ms = state["trigger_time_ms"]

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

    if poll_result.get("status") == "experiment_not_found":
        logger.warning("MLflow experiment %r not found; stopping retrain check", MLFLOW_EXPERIMENT)
        clear_retrain_state(uri)
        return poll_result

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