"""Create Prefect Cloud managed deployments for all CivicPulse flows.

Usage:
    prefect cloud login                       # once: authenticate to a workspace
    docker build -t ghcr.io/<user>/civicpulse-flows prefect/
    docker push ghcr.io/<user>/civicpulse-flows
    python deploy.py                          # creates managed work pool + 5 deployments + automation

Schedules match the original Airflow DAGs (UTC). Exactly 5 deployments (Hobby limit);
retrain-model dispatches trigger vs. event-driven check via the `mode` parameter.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FLOWS_DIR = Path(__file__).resolve().parent / "flows"
sys.path.insert(0, str(FLOWS_DIR))

from prefect.automations import AutomationCore  # noqa: E402
from prefect.client.orchestration import get_client  # noqa: E402
from prefect.client.schemas.actions import WorkPoolCreate  # noqa: E402
from prefect.client.schemas.schedules import CronSchedule  # noqa: E402
from prefect.events.actions import RunDeployment  # noqa: E402
from prefect.events.schemas.automations import EventTrigger  # noqa: E402
from prefect.exceptions import ObjectNotFound  # noqa: E402

from audit_log_archival import audit_log_archival_flow  # noqa: E402
from daily_report import daily_report_flow  # noqa: E402
from drift_detection import drift_detection_flow  # noqa: E402
from retrain_model import retrain_model_flow  # noqa: E402
from sla_monitoring import sla_monitoring_flow  # noqa: E402

WORK_POOL = os.getenv("PREFECT_WORK_POOL", "prefect-managed")
IMAGE = os.getenv("PREFECT_IMAGE", "ghcr.io/borutouzumaaki07/civicpulse-flows:latest")

# Exactly 5 deployments = Hobby plan limit. retrain-model handles both the
# weekly trigger (mode="trigger") and the event-driven poller (mode="check").
FLOWS = {
    "retrain-model": retrain_model_flow,
    "drift-detection": drift_detection_flow,
    "daily-report": daily_report_flow,
    "sla-monitoring": sla_monitoring_flow,
    "audit-log-archival": audit_log_archival_flow,
}

SCHEDULES = {
    "retrain-model": "0 3 * * 0",          # Sunday 03:00 UTC
    "drift-detection": "0 2 * * *",        # daily 02:00 UTC
    "daily-report": "0 8 * * *",           # daily 08:00 UTC
    "sla-monitoring": "0 * * * *",         # hourly (trim to 0 */4 * * * if needed)
    "audit-log-archival": "0 3 1 * *",     # 1st of month 03:00 UTC
}

DESCRIPTIONS = {
    "retrain-model": "Weekly ML retrain trigger (Sun 03:00 UTC) + event-driven poller (mode=check)",
    "drift-detection": "Detect ML model performance drift (daily 02:00 UTC)",
    "daily-report": "Generate and store daily stats report (daily 08:00 UTC)",
    "sla-monitoring": "Monitor SLA violations and escalate (hourly — trim to 0 */4 * * * for budget)",
    "audit-log-archival": "Archive old drift reports and escalation logs (monthly 03:00 UTC)",
}

# Job env vars (injected into the serverless container at runtime)
JOB_ENV_VARS = {k: v for k, v in {
    "CIVICPULSE_DB_URI": os.getenv("CIVICPULSE_DB_URI", ""),
    "CIVICPULSE_MONGO_URI": os.getenv("CIVICPULSE_MONGO_URI", ""),
    "DAGSHUB_TOKEN": os.getenv("DAGSHUB_TOKEN", ""),
}.items() if v}


def ensure_work_pool() -> None:
    with get_client(sync_client=True) as client:
        try:
            client.read_work_pool_by_name(WORK_POOL)
            print(f"Work pool '{WORK_POOL}' already exists")
        except ObjectNotFound:
            client.create_work_pool(WorkPoolCreate(name=WORK_POOL, type="managed"))
            print(f"Created work pool '{WORK_POOL}' (type=managed)")


def ensure_automation(deployment_ids: dict[str, str]) -> None:
    """Create automation: on 'civicpulse.retrain.triggered', launch a mode=check run.

    Check runs never emit that event, so they cannot re-trigger the automation (no loop).
    """
    retrain_dep_id = deployment_ids.get("retrain-model")
    if not retrain_dep_id:
        print("Skipping automation: missing retrain-model deployment ID")
        return

    with get_client(sync_client=True) as client:
        # Check if automation already exists
        try:
            existing = client.read_automation_by_name("retrain-triggers-check-training")
            print(f"Automation 'retrain-triggers-check-training' already exists")
            return
        except ObjectNotFound:
            pass

        automation = AutomationCore(
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
        )
        client.create_automation(automation)
        print("Created automation 'retrain-triggers-check-training'")


def main() -> None:
    ensure_work_pool()

    deployment_ids: dict[str, str] = {}

    with get_client(sync_client=True) as client:
        for name, flow_obj in FLOWS.items():
            cron = SCHEDULES[name]
            schedule = CronSchedule(cron=cron, timezone="UTC") if cron else None

            deployment_id = flow_obj.deploy(
                name=name,
                work_pool_name=WORK_POOL,
                image=IMAGE,
                build=False,
                push=False,
                schedule=schedule,
                description=DESCRIPTIONS[name],
                tags=["civicpulse"],
                job_variables={"env": JOB_ENV_VARS} if JOB_ENV_VARS else {},
            )
            deployment_ids[name] = deployment_id
            sched_str = cron if cron else "event-driven"
            print(f"Deployed '{name}' -> work pool '{WORK_POOL}' (schedule={sched_str})")

    ensure_automation(deployment_ids)


if __name__ == "__main__":
    main()