"""
CivicPulse Daily Report DAG
Runs daily at 8 AM to generate and store daily stats.
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


def generate_daily_report(**context):
    """Generate daily stats from PostgreSQL and store in MongoDB."""
    hook = PostgresHook(postgres_conn_id="civicpulse_db")

    stats = hook.get_pandas_df(
        """
        SELECT
            COUNT(*) as total_issues,
            COUNT(*) FILTER (WHERE status = 'reported') as reported,
            COUNT(*) FILTER (WHERE status = 'assigned') as assigned,
            COUNT(*) FILTER (WHERE status = 'in_progress') as in_progress,
            COUNT(*) FILTER (WHERE status = 'resolved') as resolved,
            COUNT(*) FILTER (WHERE status = 'verified') as verified,
            COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) as today_new,
            COUNT(*) FILTER (WHERE updated_at >= CURRENT_DATE AND status = 'resolved') as today_resolved,
            AVG(CASE WHEN resolved_at IS NOT NULL THEN
                EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600
            END) as avg_resolution_hours
        FROM issues
        """
    )

    row = stats.iloc[0]

    ward_stats = hook.get_pandas_df(
        """
        SELECT w.name as ward_name, COUNT(i.id) as issue_count
        FROM wards w
        LEFT JOIN issues i ON i.ward_id = w.id
        GROUP BY w.name
        ORDER BY issue_count DESC
        """
    )

    type_stats = hook.get_pandas_df(
        """
        SELECT issue_type, COUNT(*) as count
        FROM issues
        GROUP BY issue_type
        ORDER BY count DESC
        """
    )

    now = datetime.now(timezone.utc)
    report = {
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "total_issues": int(row["total_issues"]),
        "by_status": {
            "reported": int(row["reported"]),
            "assigned": int(row["assigned"]),
            "in_progress": int(row["in_progress"]),
            "resolved": int(row["resolved"]),
            "verified": int(row["verified"]),
        },
        "today": {
            "new_issues": int(row["today_new"]),
            "resolved_issues": int(row["today_resolved"]),
        },
        "avg_resolution_hours": round(float(row["avg_resolution_hours"] or 0), 2),
        "by_ward": ward_stats.to_dict("records"),
        "by_type": type_stats.to_dict("records"),
    }

    mongo_hook = MongoHook(mongo_conn_id="civicpulse_mongo")
    client = mongo_hook.get_conn()
    db = client["civicpulse_analytics"]
    db["daily_reports"].update_one(
        {"date": report["date"]},
        {"$set": report},
        upsert=True,
    )

    context["ti"].xcom_push(key="report", value=report)
    logger.info("Daily report generated: %s", json.dumps(report, indent=2, default=str))


with DAG(
    dag_id="daily_report",
    default_args=default_args,
    description="Generate and store daily stats report",
    schedule_interval="0 8 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["civicpulse", "reporting", "stats"],
) as dag:
    generate = PythonOperator(
        task_id="generate_daily_report",
        python_callable=generate_daily_report,
    )
