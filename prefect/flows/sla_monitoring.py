"""SLA monitoring flow: detect violations, escalate exceeded, log summary.

Port of airflow/dags/sla_monitoring.py. Original schedule: hourly.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import psycopg2
from prefect import flow, get_run_logger, task

from connections import get_db_uri, get_mongo_uri

MONGO_DB = "civicpulse_analytics"

VIOLATIONS_SQL = """
    SELECT a.id AS assignment_id, a.issue_id, a.sla_deadline, a.status,
           e.id AS engineer_id, u.email AS engineer_email, u.full_name,
           i.issue_type, i.severity
    FROM assignments a
    JOIN engineers e ON a.engineer_id = e.id
    JOIN users u ON e.user_id = u.id
    JOIN issues i ON a.issue_id = i.id
    WHERE a.status IN ('pending', 'accepted', 'in_progress')
      AND a.sla_deadline IS NOT NULL
"""


@task(retries=1, retry_delay_seconds=300)
def check_sla_violations(db_uri: str) -> list[dict]:
    logger = get_run_logger()
    now = datetime.now(timezone.utc)

    with psycopg2.connect(db_uri) as conn, conn.cursor() as cur:
        cur.execute(VIOLATIONS_SQL)
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]

    violations: list[dict] = []
    for row in rows:
        rec = dict(zip(cols, row))
        sla_deadline = rec["sla_deadline"]
        if isinstance(sla_deadline, str):
            sla_deadline = datetime.fromisoformat(sla_deadline)

        hours_remaining = (sla_deadline - now).total_seconds() / 3600
        if hours_remaining < 0:
            violations.append(
                {
                    "type": "exceeded",
                    "assignment_id": int(rec["assignment_id"]),
                    "issue_id": int(rec["issue_id"]),
                    "engineer_id": int(rec["engineer_id"]),
                    "engineer_email": rec["engineer_email"],
                    "hours_overdue": round(abs(hours_remaining), 1),
                    "severity": int(rec["severity"]),
                }
            )
        elif hours_remaining < 4:
            violations.append(
                {
                    "type": "approaching",
                    "assignment_id": int(rec["assignment_id"]),
                    "issue_id": int(rec["issue_id"]),
                    "engineer_id": int(rec["engineer_id"]),
                    "engineer_email": rec["engineer_email"],
                    "hours_remaining": round(hours_remaining, 1),
                    "severity": int(rec["severity"]),
                }
            )

    logger.info("Found %d SLA violations/approaching", len(violations))
    return violations


@task(retries=1, retry_delay_seconds=300)
def escalate_violations(db_uri: str, mongo_uri: str, violations: list[dict]) -> None:
    logger = get_run_logger()
    exceeded = [v for v in violations if v["type"] == "exceeded"]
    if not exceeded:
        logger.info("No exceeded SLAs to escalate")
        return

    with psycopg2.connect(db_uri) as conn:
        with conn.cursor() as cur:
            for v in exceeded:
                cur.execute(
                    """
                    UPDATE assignments
                    SET status = 'in_progress'
                    WHERE id = %s AND status != 'completed'
                    """,
                    (v["assignment_id"],),
                )

    from pymongo import MongoClient

    with MongoClient(mongo_uri) as client:
        client[MONGO_DB]["escalation_logs"].insert_many(exceeded)

    logger.info("Escalated %d exceeded SLA assignments", len(exceeded))


@task
def log_sla_summary(mongo_uri: str, violations: list[dict]) -> None:
    logger = get_run_logger()
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_violations": len(violations),
        "exceeded": len([v for v in violations if v["type"] == "exceeded"]),
        "approaching": len([v for v in violations if v["type"] == "approaching"]),
    }

    from pymongo import MongoClient

    with MongoClient(mongo_uri) as client:
        client[MONGO_DB]["sla_reports"].insert_one(dict(summary))
    logger.info("SLA summary: %s", json.dumps(summary))


@flow(
    name="sla-monitoring",
    description="Monitor SLA violations and escalate",
    log_prints=True,
)
def sla_monitoring_flow() -> list[dict]:
    db_uri = get_db_uri()
    mongo_uri = get_mongo_uri()
    violations = check_sla_violations(db_uri)
    escalate_violations(db_uri, mongo_uri, violations)
    log_sla_summary(mongo_uri, violations)
    return violations
