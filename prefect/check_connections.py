"""Verify Prefect flow connectivity (DB, Mongo) via prefect/.env.

Run from the repo root with the pixi prefect env:

    pixi run -e prefect python prefect/check_connections.py

Exit code 0 = all checks passed, non-zero = at least one failed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FLOWS_DIR = Path(__file__).resolve().parent / "flows"
sys.path.insert(0, str(FLOWS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from load_env import load_prefect_env  # noqa: E402
from connections import get_db_uri, get_mongo_uri  # noqa: E402


def check() -> int:
    load_prefect_env()
    failures = 0

    try:
        db_uri = get_db_uri()
        scheme = db_uri.split("://", 1)[0]
        print(f"[DB ] URI resolved, scheme={scheme!r}")
        if scheme.startswith("postgresql+") or "asyncpg" in scheme:
            print("  ERROR: flows use psycopg2 and cannot parse the asyncpg scheme.")
            print("  Use a plain postgresql:// URI in CIVICPULSE_DB_URI.")
            failures += 1
        else:
            import psycopg2

            conn = psycopg2.connect(db_uri, connect_timeout=10)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                (row,) = cur.fetchone()
            conn.close()
            print(f"  OK: psycopg2 connected, SELECT 1 -> {row}")
    except Exception as exc:  # noqa: BLE001
        print(f"[DB ] FAIL: {exc}")
        failures += 1

    try:
        mongo_uri = get_mongo_uri()
        host = mongo_uri.split("@")[-1].split("/")[0]
        print(f"[MONGO] URI resolved, host={host!r}")
        from pymongo import MongoClient

        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
        client.close()
        print("  OK: MongoDB ping succeeded")
    except Exception as exc:  # noqa: BLE001
        print(f"[MONGO] FAIL: {exc}")
        print("  If 'no replica set members found' -> check Atlas Network Access IP allowlist.")
        failures += 1

    token = os.getenv("DAGSHUB_TOKEN")
    user = os.getenv("DAGSHUB_USERNAME", "")
    repo = os.getenv("DAGSHUB_REPO", "")
    if not token or token.startswith("<"):
        print("[DAGSHUB] WARN: DAGSHUB_TOKEN not set locally (retrain needs it or the Secret block)")
    else:
        print(f"[DAGSHUB] OK: token set ({len(token)} chars) for {user}/{repo}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(check())
