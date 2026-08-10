"""Daily report flow: aggregate Postgres issue stats, upsert into Mongo.

Schedule: daily 08:00 UTC.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import psycopg2
from prefect import flow, get_run_logger, task

from connections import get_db_uri, get_mongo_uri

MONGO_DB = "civicpulse_analytics"

ISSUES_SQL = """
    SELECT
        COUNT(*) AS total_issues,
        COUNT(*) FILTER (WHERE status = 'reported') AS reported,
        COUNT(*) FILTER (WHERE status = 'assigned') AS assigned,
        COUNT(*) FILTER (WHERE status = 'in_progress') AS in_progress,
        COUNT(*) FILTER (WHERE status = 'resolved') AS resolved,
        COUNT(*) FILTER (WHERE status = 'verified') AS verified,
        COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today_new,
        COUNT(*) FILTER (WHERE updated_at >= CURRENT_DATE AND status = 'resolved') AS today_resolved,
        AVG(CASE WHEN resolved_at IS NOT NULL THEN
            EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600
        END) AS avg_resolution_hours
    FROM issues
"""

WARD_SQL = """
    SELECT w.name AS ward_name, COUNT(i.id) AS issue_count
    FROM wards w
    LEFT JOIN issues i ON i.ward_id = w.id
    GROUP BY w.name
    ORDER BY issue_count DESC
"""

TYPE_SQL = """
    SELECT issue_type, COUNT(*) AS count
    FROM issues
    GROUP BY issue_type
    ORDER BY count DESC
"""


@task(retries=1, retry_delay_seconds=300)
def query_stats(db_uri: str) -> dict:
    logger = get_run_logger()

    with psycopg2.connect(db_uri) as conn, conn.cursor() as cur:
        cur.execute(ISSUES_SQL)
        issues = cur.fetchone()

        cur.execute(WARD_SQL)
        wards = [{"ward_name": r[0], "issue_count": r[1]} for r in cur.fetchall()]

        cur.execute(TYPE_SQL)
        types = [{"issue_type": r[0], "count": r[1]} for r in cur.fetchall()]

    now = datetime.now(timezone.utc)
    report = {
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "total_issues": int(issues[0]),
        "by_status": {
            "reported": int(issues[1]),
            "assigned": int(issues[2]),
            "in_progress": int(issues[3]),
            "resolved": int(issues[4]),
            "verified": int(issues[5]),
        },
        "today": {
            "new_issues": int(issues[6]),
            "resolved_issues": int(issues[7]),
        },
        "avg_resolution_hours": round(float(issues[8] or 0), 2),
        "by_ward": wards,
        "by_type": types,
    }
    logger.info("Daily report generated: %s", json.dumps(report, indent=2, default=str))
    return report


@task(retries=1, retry_delay_seconds=300)
def upsert_report(mongo_uri: str, report: dict) -> None:
    from pymongo import MongoClient

    with MongoClient(mongo_uri) as client:
        client[MONGO_DB]["daily_reports"].update_one(
            {"date": report["date"]},
            {"$set": report},
            upsert=True,
        )


@flow(
    name="daily-report",
    description="Generate and store daily stats report",
    log_prints=True,
)
def daily_report_flow() -> dict:
    db_uri = get_db_uri()
    mongo_uri = get_mongo_uri()
    report = query_stats(db_uri)
    upsert_report(mongo_uri, report)
    return report
