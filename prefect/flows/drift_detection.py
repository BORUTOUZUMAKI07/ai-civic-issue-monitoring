"""Drift detection flow: fetch recent predictions, write a drift report.

Monitors:
  - Confidence score distribution (mean, std)
  - Class distribution (predicted label frequencies)
  - Prediction entropy (model uncertainty across classes)

Baselines are computed from the first batch of predictions stored in
``drift_baselines`` (bootstrapped on first run) instead of hardcoded.

Alerts via Slack webhook and/or SMTP email when drift is detected.
On HIGH drift, emits ``civicpulse.drift.high`` so the retrain automation
can pick it up.

Schedule: daily 02:00 UTC.
"""
from __future__ import annotations

import math
import os
import smtplib
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

import requests
from prefect import flow, get_run_logger, task

from connections import get_mongo_uri

MONGO_DB = "civicpulse_analytics"

# ── Thresholds ──────────────────────────────────────────────────────────
CONF_MEAN_DRIFT_WARN = 0.15      # 15 % relative drift → medium
CONF_MEAN_DRIFT_HIGH = 0.30      # 30 % → high
CONF_STD_DRIFT_WARN = 0.25
CONF_STD_DRIFT_HIGH = 0.50
CLASS_JS_WARN = 0.05             # Jensen-Shannon divergence warn
CLASS_JS_HIGH = 0.15             # JS high
ENTROPY_DRIFT_WARN = 0.15        # relative entropy change warn
ENTROPY_DRIFT_HIGH = 0.30        # relative entropy change high

MIN_SAMPLES = 10


# ── Baseline helpers ────────────────────────────────────────────────────

def _js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """Jensen-Shannon divergence between two discrete distributions."""
    all_keys = set(p) | set(q)
    m = {}
    for k in all_keys:
        m[k] = 0.5 * (p.get(k, 0.0) + q.get(k, 0.0))

    def _kl(a: dict[str, float], b: dict[str, float]) -> float:
        s = 0.0
        for k in set(a) | set(b):
            av, bv = a.get(k, 0.0), b.get(k, 0.0)
            if av > 0 and bv > 0:
                s += av * math.log(av / bv)
        return s

    return 0.5 * _kl(p, m) + 0.5 * _kl(q, m)


def _entropy(dist: dict[str, float]) -> float:
    """Shannon entropy of a discrete distribution."""
    return -sum(v * math.log(v) for v in dist.values() if v > 0)


@task(retries=1, retry_delay_seconds=300)
def get_or_create_baselines(uri: str) -> dict:
    """Load stored baselines; if missing, bootstrap from first 200 predictions."""
    from pymongo import MongoClient

    with MongoClient(uri) as client:
        db = client[MONGO_DB]
        stored = db["drift_baselines"].find_one({"_id": "current"})
        if stored:
            return stored

        # Bootstrap: use earliest 200 predictions as baseline period
        bootstrap = list(
            db["predictions"].find(
                {},
                {"_id": 0, "predicted_label": 1, "confidence": 1},
            )
            .sort("created_at", 1)
            .limit(200)
        )
        if len(bootstrap) < MIN_SAMPLES:
            raise RuntimeError(
                f"Cannot bootstrap baselines: only {len(bootstrap)} predictions exist "
                f"(need {MIN_SAMPLES}). Wait for more data."
            )

        confs = [p["confidence"] for p in bootstrap if p.get("confidence") is not None]
        labels = [p["predicted_label"] for p in bootstrap if p.get("predicted_label")]
        total = len(labels) if labels else 1
        class_dist = {k: v / total for k, v in Counter(labels).items()}

        baselines = {
            "_id": "current",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sample_count": len(confs),
            "mean_confidence": round(statistics.mean(confs), 4),
            "std_confidence": round(statistics.pstdev(confs), 4),
            "class_distribution": class_dist,
            "entropy": round(_entropy(class_dist), 4),
        }
        db["drift_baselines"].update_one(
            {"_id": "current"}, {"$set": baselines}, upsert=True
        )
        return baselines


# ── Data fetching ───────────────────────────────────────────────────────

@task(retries=1, retry_delay_seconds=300)
def fetch_recent_predictions(uri: str, days: int = 7) -> list[dict]:
    from pymongo import MongoClient

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with MongoClient(uri) as client:
        return list(
            client[MONGO_DB]["predictions"].find(
                {"created_at": {"$gte": cutoff}},
                {"_id": 0, "predicted_label": 1, "confidence": 1, "actual_label": 1},
            )
        )


# ── Core detection ──────────────────────────────────────────────────────

@task
def detect_drift(uri: str, predictions: list[dict], baselines: dict) -> dict | None:
    from pymongo import MongoClient

    logger = get_run_logger()

    if not predictions:
        logger.info("No predictions found, skipping drift detection")
        return None

    confidences = [p["confidence"] for p in predictions if p.get("confidence") is not None]
    labels = [p["predicted_label"] for p in predictions if p.get("predicted_label")]

    if len(confidences) < MIN_SAMPLES:
        logger.info("Not enough data for drift detection (%d samples)", len(confidences))
        return None

    # ── 1. Confidence score drift ───────────────────────────────────
    mean_conf = statistics.mean(confidences)
    std_conf = statistics.pstdev(confidences)
    base_mean = baselines["mean_confidence"]
    base_std = baselines["std_confidence"]

    mean_drift = abs(mean_conf - base_mean) / base_mean if base_mean else 0
    std_drift = abs(std_conf - base_std) / base_std if base_std else 0

    # ── 2. Class distribution drift (Jensen-Shannon divergence) ─────
    total = len(labels) if labels else 1
    current_dist = {k: v / total for k, v in Counter(labels).items()}
    base_dist = baselines.get("class_distribution", {})
    js_class = _js_divergence(current_dist, base_dist) if base_dist else 0

    # ── 3. Prediction entropy drift ─────────────────────────────────
    current_entropy = _entropy(current_dist) if current_dist else 0
    base_entropy = baselines.get("entropy", 0)
    entropy_drift = (
        abs(current_entropy - base_entropy) / base_entropy if base_entropy else 0
    )

    # ── Aggregate severity ──────────────────────────────────────────
    scores = [mean_drift, std_drift, js_class / CLASS_JS_WARN, entropy_drift / ENTROPY_DRIFT_WARN]
    max_norm = max(scores)

    if max_norm >= 2.0 or mean_drift > CONF_MEAN_DRIFT_HIGH or js_class > CLASS_JS_HIGH:
        severity = "high"
    elif max_norm >= 1.0 or mean_drift > CONF_MEAN_DRIFT_WARN or js_class > CLASS_JS_WARN:
        severity = "medium"
    else:
        severity = "low"

    drift_detected = severity in ("medium", "high")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(confidences),
        # confidence metrics
        "mean_confidence": round(mean_conf, 4),
        "std_confidence": round(std_conf, 4),
        "mean_drift_pct": round(mean_drift * 100, 2),
        "std_drift_pct": round(std_drift * 100, 2),
        # class distribution metrics
        "class_distribution": current_dist,
        "js_divergence": round(js_class, 4),
        # entropy metrics
        "current_entropy": round(current_entropy, 4),
        "entropy_drift_pct": round(entropy_drift * 100, 2),
        # aggregate
        "drift_detected": drift_detected,
        "severity": severity,
    }

    with MongoClient(uri) as client:
        client[MONGO_DB]["drift_reports"].insert_one(report)
    if drift_detected and severity == "high":
        logger.warning(
            "HIGH drift detected! conf_mean: %.2f%%, JS class: %.4f, entropy: %.2f%%",
            mean_drift * 100,
            js_class,
            entropy_drift * 100,
        )
    logger.info("Drift report: %s", {k: v for k, v in report.items() if k != "class_distribution"})
    return report


# ── Alerting ────────────────────────────────────────────────────────────

@task
def send_alerts(report: dict) -> None:
    logger = get_run_logger()
    severity = report.get("severity", "low")
    if severity == "low":
        return

    title = f"🚨 CivicPulse Drift Alert — {severity.upper()}"
    body_lines = [
        f"Severity: {severity.upper()}",
        f"Sample count: {report['sample_count']}",
        f"Mean confidence: {report['mean_confidence']:.4f} (drift {report['mean_drift_pct']:.1f}%)",
        f"Std confidence: {report['std_confidence']:.4f} (drift {report['std_drift_pct']:.1f}%)",
        f"JS divergence (class dist): {report['js_divergence']:.4f}",
        f"Entropy drift: {report['entropy_drift_pct']:.1f}%",
        f"Class distribution: {report.get('class_distribution', {})}",
        f"Timestamp: {report['timestamp']}",
    ]
    body = "\n".join(body_lines)

    # ── Slack ───────────────────────────────────────────────────────
    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if slack_url:
        try:
            requests.post(
                slack_url,
                json={"text": f"*{title}*\n```{body}```"},
                timeout=10,
            )
            logger.info("Slack alert sent")
        except Exception as exc:
            logger.warning("Slack alert failed: %s", exc)

    # ── Email ───────────────────────────────────────────────────────
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    alert_to = os.getenv("ALERT_EMAIL_TO", "")

    if smtp_host and alert_to:
        try:
            msg = MIMEText(body)
            msg["Subject"] = title
            msg["From"] = smtp_user or "civicpulse@alerts"
            msg["To"] = alert_to

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
                s.starttls()
                if smtp_user and smtp_pass:
                    s.login(smtp_user, smtp_pass)
                s.sendmail(msg["From"], [alert_to], msg.as_string())
            logger.info("Email alert sent to %s", alert_to)
        except Exception as exc:
            logger.warning("Email alert failed: %s", exc)


# ── Auto-retrain trigger ────────────────────────────────────────────────

@task
def maybe_trigger_retrain(report: dict) -> None:
    """Emit event to trigger retrain on HIGH drift."""
    if report.get("severity") != "high":
        return

    from prefect.events import emit_event

    logger = get_run_logger()
    emit_event(
        event="civicpulse.drift.high",
        resource={
            "prefect.resource.id": "civicpulse.drift",
            "prefect.resource.name": "drift-detection",
        },
        payload={
            "severity": "high",
            "mean_drift_pct": report.get("mean_drift_pct", 0),
            "js_divergence": report.get("js_divergence", 0),
        },
    )
    logger.warning("Emitted civicpulse.drift.high — retrain automation should pick this up")


# ── Flow ────────────────────────────────────────────────────────────────

@flow(
    name="drift-detection",
    description="Detect ML model drift: confidence, class distribution, and entropy",
    log_prints=True,
)
def drift_detection_flow() -> dict | None:
    uri = get_mongo_uri()
    baselines = get_or_create_baselines(uri)
    predictions = fetch_recent_predictions(uri)
    report = detect_drift(uri, predictions, baselines)
    if report and report.get("drift_detected"):
        send_alerts(report)
        maybe_trigger_retrain(report)
    return report
