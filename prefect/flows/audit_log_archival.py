"""Audit log archival flow: move >90-day docs to archived_* collections.

Schedule: 1st of month 03:00 UTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prefect import flow, get_run_logger, task

from connections import get_mongo_uri

MONGO_DB = "civicpulse_analytics"
# `audit_logs` is compliance evidence: it is archived to a cold collection,
# never deleted. The report's retention policy mirrors this list in the API.
COLLECTIONS = ["drift_reports", "sla_reports", "escalation_logs", "audit_logs"]


@task(retries=2, retry_delay_seconds=60)
def archive_old_logs(uri: str, cutoff_days: int = 90) -> int:
    logger = get_run_logger()
    # Store a real BSON datetime, not an ISO string: comparing a string against
    # the datetimes Beanie writes never matches, so the old flow silently
    # archived nothing even though it reported success.
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    total = 0

    from pymongo import MongoClient, UpdateOne

    with MongoClient(uri) as client:
        db = client[MONGO_DB]
        for name in COLLECTIONS:
            old_docs = list(db[name].find({"timestamp": {"$lt": cutoff}}))
            if old_docs:
                # Upsert on the preserved _id instead of insert_many. A retry
                # after a partial run (archive written, source not yet deleted)
                # used to raise DuplicateKeyError and fail the whole flow; now
                # it either leaves the first archived copy intact ($setOnInsert)
                # or, if the delete already happened, finds nothing to do.
                archive = db[f"archived_{name}"]
                archive.bulk_write(
                    [
                        UpdateOne({"_id": doc["_id"]}, {"$setOnInsert": doc}, upsert=True)
                        for doc in old_docs
                    ],
                    ordered=False,
                )
                ids = [d["_id"] for d in old_docs]
                db[name].delete_many({"_id": {"$in": ids}})
                total += len(old_docs)
                logger.info("Archived %d documents from %s", len(old_docs), name)

    logger.info("Total archived: %d", total)
    return total


@flow(
    name="audit-log-archival",
    description="Archive old audit events, drift reports and escalation logs to cold storage",
    log_prints=True,
)
def audit_log_archival_flow() -> int:
    return archive_old_logs(get_mongo_uri())
