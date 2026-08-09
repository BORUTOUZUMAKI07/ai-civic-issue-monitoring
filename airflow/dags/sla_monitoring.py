"""
CivicPulse SLA Monitoring DAG
Runs every hour to check for SLA violations and escalate.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.mongo.hooks.mongo import MongoHook

logger = logging.getLogger(__name__)

default_args = {
    "owner": "civicpulse",
    "depends_on_past": False,
    "email_on_failure": True,
    "email": ["admin@civicpulse.com"],
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def check_sla_violations(**context):
    """Check for issues approaching or exceeding SLA deadline."""
    hook = PostgresHook(postgres_conn_id="civicpulse_db")

    rows = hook.get_pandas_df(
        """
        SELECT a.id as assignment_id, a.issue_id, a.sla_deadline, a.status,
               e.id as engineer_id, u.email as engineer_email, u.full_name,
               i.issue_type, i.severity
        FROM assignments a
        JOIN engineers e ON a.engineer_id = e.id
        JOIN users u ON e.user_id = u.id
        JOIN issues i ON a.issue_id = i.id
        WHERE a.status IN ('pending', 'accepted', 'in_progress')
          AND a.sla_deadline IS NOT NULL
        """
    )

    violations = []
    now = datetime.now(timezone.utc)

    for _, row in rows.iterrows():
        sla_deadline = row["sla_deadline"]
        if isinstance(sla_deadline, str):
            sla_deadline = datetime.fromisoformat(sla_deadline)

        hours_remaining = (sla_deadline - now).total_seconds() / 3600

        if hours_remaining < 0:
            violations.append({
                "type": "exceeded",
                "assignment_id": int(row["assignment_id"]),
                "issue_id": int(row["issue_id"]),
                "engineer_id": int(row["engineer_id"]),
                "engineer_email": row["engineer_email"],
                "hours_overdue": round(abs(hours_remaining), 1),
                "severity": int(row["severity"]),
            })
        elif hours_remaining < 4:
            violations.append({
                "type": "approaching",
                "assignment_id": int(row["assignment_id"]),
                "issue_id": int(row["issue_id"]),
                "engineer_id": int(row["engineer_id"]),
                "engineer_email": row["engineer_email"],
                "hours_remaining": round(hours_remaining, 1),
                "severity": int(row["severity"]),
            })

    context["ti"].xcom_push(key="violations", value=violations)
    logger.info("Found %d SLA violations/approaching", len(violations))
    return violations


def escalate_violations(**context):
    """Escalate exceeded SLAs: mark assignments as in_progress and notify via MongoDB."""
    violations = context["ti"].xcom_pull(key="violations", task_ids="check_sla_violations")
    exceeded = [v for v in violations if v["type"] == "exceeded"]

    if not exceeded:
        logger.info("No exceeded SLAs to escalate")
        return

    hook = PostgresHook(postgres_conn_id="civicpulse_db")

    for v in exceeded:
        hook.run(
            """
            UPDATE assignments
            SET status = 'in_progress'
            WHERE id = %s AND status != 'completed'
            """,
            parameters=(v["assignment_id"],),
        )

    mongo_hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = mongo_hook.get_conn()
    db = client["civicpulse_analytics"]
    db["escalation_logs"].insert_many(exceeded)

    logger.info("Escalated %d exceeded SLA assignments", len(exceeded))


def log_sla_summary(**context):
    """Log SLA check summary to MongoDB."""
    violations = context["ti"].xcom_pull(key="violations", task_ids="check_sla_violations")

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_violations": len(violations),
        "exceeded": len([v for v in violations if v["type"] == "exceeded"]),
        "approaching": len([v for v in violations if v["type"] == "approaching"]),
    }

    mongo_hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = mongo_hook.get_conn()
    db = client["civicpulse_analytics"]
    db["sla_reports"].insert_one(summary)

    logger.info("SLA summary: %s", json.dumps(summary))


with DAG(
    dag_id="sla_monitoring",
    default_args=default_args,
    description="Monitor SLA violations and escalate",
    schedule="0 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["civicpulse", "sla", "escalation"],
) as dag:
    check = PythonOperator(
        task_id="check_sla_violations",
        python_callable=check_sla_violations,
    )

    escalate = PythonOperator(
        task_id="escalate_violations",
        python_callable=escalate_violations,
    )

    summary = PythonOperator(
        task_id="log_sla_summary",
        python_callable=log_sla_summary,
    )

    check >> escalate >> summary
