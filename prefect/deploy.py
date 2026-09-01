"""Create Prefect Cloud managed deployments for all CivicPulse flows.

Managed execution (Prefect Managed) only runs official Prefect images, so code is
pulled from git at run time via `flow.from_source`, and Python dependencies are
installed on the serverless container via `pip_packages`.

Code source: the public DagsHub mirror of this repo (GitHub's public clone is
currently unreachable for this account). Auth uses the `dagshub-token` Secret
block, so no token is embedded in the deployment config.

Usage:
    prefect cloud login                       # once: authenticate to a workspace
    python deploy.py                          # creates managed work pool + 5 deployments + automation

Schedules are UTC. Exactly 5 deployments (Hobby limit);
retrain-model dispatches trigger vs. event-driven check via the `mode` parameter.
Two automations: retrain-triggered and drift-high-triggers-retrain.
"""
from __future__ import annotations

import os

from prefect import flow
from prefect.automations import AutomationCore  # noqa: E402
from prefect.blocks.system import Secret  # noqa: E402
from prefect.client.orchestration import get_client  # noqa: E402
from prefect.client.schemas.actions import WorkPoolCreate  # noqa: E402
from prefect.client.schemas.schedules import CronSchedule  # noqa: E402
from prefect.events.actions import RunDeployment  # noqa: E402
from prefect.events.schemas.automations import EventTrigger  # noqa: E402
from prefect.exceptions import ObjectNotFound  # noqa: E402
from prefect.runner.storage import GitRepository  # noqa: E402

WORK_POOL = os.getenv("PREFECT_WORK_POOL", "civicpulse-managed")

DAGSHUB_USER = os.getenv("DAGSHUB_USERNAME", "")
DAGSHUB_REPO = os.getenv("DAGSHUB_REPO", "ai-civic-issue-monitoring")
DAGSHUB_GIT_URL = f"https://dagshub.com/{DAGSHUB_USER}/{DAGSHUB_REPO}.git"
SOURCE = GitRepository(
    url=DAGSHUB_GIT_URL,
    credentials={"access_token": Secret.load("dagshub-token")},
)

# Python packages installed on the serverless container at run time
# (the base image already includes `prefect`).
PIP_PACKAGES = ["pymongo>=4.6,<5", "psycopg2-binary>=2.9", "requests>=2.31"]

# Exactly 5 deployments = Hobby plan limit. retrain-model handles both the
# weekly trigger (mode="trigger") and the event-driven poller (mode="check").
FLOWS = {
    "retrain-model": "prefect/flows/retrain_model.py:retrain_model_flow",
    "drift-detection": "prefect/flows/drift_detection.py:drift_detection_flow",
    "daily-report": "prefect/flows/daily_report.py:daily_report_flow",
    "sla-monitoring": "prefect/flows/sla_monitoring.py:sla_monitoring_flow",
    "audit-log-archival": "prefect/flows/audit_log_archival.py:audit_log_archival_flow",
}

SCHEDULES = {
    "retrain-model": "0 3 * * 0",          # Sunday 03:00 UTC
    "drift-detection": "0 2 * * *",        # daily 02:00 UTC
    "daily-report": "0 8 * * *",           # daily 08:00 UTC
    "sla-monitoring": "0 */6 * * *",       # every 6 hours to stay within free-tier compute budget
    "audit-log-archival": "0 3 1 * *",     # 1st of month 03:00 UTC
}

DESCRIPTIONS = {
    "retrain-model": "Weekly ML retrain trigger (Sun 03:00 UTC) + event-driven poller (mode=check)",
    "drift-detection": "Detect ML model drift: confidence, class distribution, entropy (daily 02:00 UTC)",
    "daily-report": "Generate and store daily stats report (daily 08:00 UTC)",
    "sla-monitoring": "Monitor SLA violations and escalate (every 6 hours to fit free-tier compute budget)",
    "audit-log-archival": "Archive old drift reports and escalation logs (monthly 03:00 UTC)",
}

# Job env vars (injected into the serverless container at runtime)
JOB_ENV_VARS = {k: v for k, v in {
    "CIVICPULSE_DB_URI": os.getenv("CIVICPULSE_DB_URI", ""),
    "CIVICPULSE_MONGO_URI": os.getenv("CIVICPULSE_MONGO_URI", ""),
    "DAGSHUB_TOKEN": os.getenv("DAGSHUB_TOKEN", ""),
    # Drift alerting (drift-detection flow)
    "SLACK_WEBHOOK_URL": os.getenv("SLACK_WEBHOOK_URL", ""),
    "SMTP_HOST": os.getenv("SMTP_HOST", ""),
    "SMTP_PORT": os.getenv("SMTP_PORT", ""),
    "SMTP_USER": os.getenv("SMTP_USER", ""),
    "SMTP_PASS": os.getenv("SMTP_PASS", ""),
    "ALERT_EMAIL_TO": os.getenv("ALERT_EMAIL_TO", ""),
}.items() if v}

JOB_VARIABLES = {"pip_packages": PIP_PACKAGES}
if JOB_ENV_VARS:
    JOB_VARIABLES["env"] = JOB_ENV_VARS


def ensure_work_pool() -> None:
    with get_client(sync_client=True) as client:
        try:
            client.read_work_pool(WORK_POOL)
            print(f"Work pool '{WORK_POOL}' already exists")
        except ObjectNotFound:
            client.create_work_pool(WorkPoolCreate(name=WORK_POOL, type="prefect:managed"))
            print(f"Created work pool '{WORK_POOL}' (type=prefect:managed)")


def ensure_automations(deployment_ids: dict[str, str]) -> None:
    """Create automations for retrain triggering.

    1. ``retrain-triggers-check-training``: on ``civicpulse.retrain.triggered``
       (weekly cron), launch a mode=check run.
    2. ``drift-high-triggers-retrain``: on ``civicpulse.drift.high``
       (emitted by drift-detection when severity=high), launch a mode=trigger
       run which pushes an empty commit and starts training.
    """
    retrain_dep_id = deployment_ids.get("retrain-model")
    if not retrain_dep_id:
        print("Skipping automations: missing retrain-model deployment ID")
        return

    with get_client(sync_client=True) as client:
        # ── Automation 1: retrain.triggered → mode=check ────────────
        try:
            existing = client.read_automations_by_name("retrain-triggers-check-training")
            if existing:
                print("Automation 'retrain-triggers-check-training' already exists")
            else:
                raise ObjectNotFound("not found")
        except ObjectNotFound:
            client.create_automation(AutomationCore(
                name="retrain-triggers-check-training",
                description=(
                    "When retrain-model emits 'civicpulse.retrain.triggered', launch a "
                    "mode=check run which polls MLflow and self-reschedules until done."
                ),
                enabled=True,
                trigger=EventTrigger(
                    expect={"civicpulse.retrain.triggered"},
                    match={"prefect.resource.name": "retrain-model"},
                ),
                actions=[RunDeployment(deployment_id=retrain_dep_id, parameters={"mode": "check"})],
            ))
            print("Created automation 'retrain-triggers-check-training'")

        # ── Automation 2: drift.high → mode=trigger ─────────────────
        try:
            existing = client.read_automations_by_name("drift-high-triggers-retrain")
            if existing:
                print("Automation 'drift-high-triggers-retrain' already exists")
            else:
                raise ObjectNotFound("not found")
        except ObjectNotFound:
            client.create_automation(AutomationCore(
                name="drift-high-triggers-retrain",
                description=(
                    "When drift-detection emits 'civicpulse.drift.high', launch a "
                    "retrain-model run in trigger mode (pushes empty commit to start training)."
                ),
                enabled=True,
                trigger=EventTrigger(
                    expect={"civicpulse.drift.high"},
                    match={"prefect.resource.name": "drift-detection"},
                ),
                actions=[RunDeployment(deployment_id=retrain_dep_id, parameters={"mode": "trigger"})],
            ))
            print("Created automation 'drift-high-triggers-retrain'")


def main() -> None:
    ensure_work_pool()

    deployment_ids: dict[str, str] = {}

    for name, entrypoint in FLOWS.items():
        cron = SCHEDULES[name]
        schedule = CronSchedule(cron=cron, timezone="UTC") if cron else None

        deployment_id = flow.from_source(source=SOURCE, entrypoint=entrypoint).deploy(
            name=name,
            work_pool_name=WORK_POOL,
            build=False,
            push=False,
            schedule=schedule,
            description=DESCRIPTIONS[name],
            tags=["civicpulse"],
            job_variables=JOB_VARIABLES,
        )
        deployment_ids[name] = str(deployment_id)
        sched_str = cron if cron else "event-driven"
        print(f"Deployed '{name}' -> work pool '{WORK_POOL}' (schedule={sched_str})")

    ensure_automations(deployment_ids)


if __name__ == "__main__":
    main()
