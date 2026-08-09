"""Audit log archival flow: move >90-day docs to archived_* collections.

Port of airflow/dags/audit_log_archival.py. Original schedule: 1st of month 03:00 UTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prefect import flow, get_run_logger, task

from connections import get_mongo_uri

MONGO_DB = "civicpulse_analytics"
COLLECTIONS = ["drift_reports", "sla_reports", "escalation_logs"]


@task(retries=1, retry_delay_seconds=600)
def archive_old_logs(uri: str, cutoff_days: int = 90) -> int:
    logger = get_run_logger()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=cutoff_days)).isoformat()
    total = 0

    from pymongo import MongoClient

    with MongoClient(uri) as client:
        db = client[MONGO_DB]
        for name in COLLECTIONS:
            old_docs = list(db[name].find({"timestamp": {"$lt": cutoff}}))
            if old_docs:
                db[f"archived_{name}"].insert_many(old_docs, ordered=False)
                ids = [d["_id"] for d in old_docs]
                db[name].delete_many({"_id": {"$in": ids}})
                total += len(old_docs)
                logger.info("Archived %d documents from %s", len(old_docs), name)

    logger.info("Total archived: %d", total)
    return total


@flow(
    name="audit-log-archival",
    description="Archive old drift reports and escalation logs to cold storage",
    log_prints=True,
)
def audit_log_archival_flow() -> int:
    return archive_old_logs(get_mongo_uri())
