"""
CivicPulse Audit Log Archival DAG
Runs monthly to archive old drift reports and escalation logs from MongoDB.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator
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


def archive_old_logs(**context):
    """Move drift reports and escalation logs older than 90 days to archive collection."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)

    mongo_hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = mongo_hook.get_conn()
    db = client["civicpulse_analytics"]

    collections_to_archive = ["drift_reports", "sla_reports", "escalation_logs"]
    total_archived = 0

    for collection_name in collections_to_archive:
        source = db[collection_name]
        target = db[f"archived_{collection_name}"]

        old_docs = list(source.find({"timestamp": {"$lt": cutoff_date.isoformat()}}))
        if old_docs:
            target.insert_many(old_docs, ordered=False)
            ids = [doc["_id"] for doc in old_docs]
            source.delete_many({"_id": {"$in": ids}})
            total_archived += len(old_docs)
            logger.info("Archived %d documents from %s", len(old_docs), collection_name)

    context["ti"].xcom_push(key="archived_count", value=total_archived)
    logger.info("Total archived: %d", total_archived)


def log_archive_summary(**context):
    """Log archival summary."""
    count = context["ti"].xcom_pull(key="archived_count", task_ids="archive_old_logs") or 0

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "archived_count": count,
        "cutoff_days": 90,
    }
    logger.info("Archive summary: %s", json.dumps(summary))


with DAG(
    dag_id="audit_log_archival",
    default_args=default_args,
    description="Archive old drift reports and escalation logs to cold storage",
    schedule="0 3 1 * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["civicpulse", "archive", "maintenance"],
) as dag:
    archive = PythonOperator(
        task_id="archive_old_logs",
        python_callable=archive_old_logs,
    )

    log_summary = PythonOperator(
        task_id="log_archive_summary",
        python_callable=log_archive_summary,
    )

    archive >> log_summary
