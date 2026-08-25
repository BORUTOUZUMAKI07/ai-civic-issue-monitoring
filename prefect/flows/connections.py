"""Resolve CivicPulse service credentials for Prefect flows.

Precedence: environment variable -> Prefect Secret block (token only).

Env vars (primary, set on the worker / in .env):
    - CIVICPULSE_DB_URI      (or DATABASE_URL)      Postgres connection URI
    - CIVICPULSE_MONGO_URI   (or MONGODB_URI)       MongoDB connection URI
    - DAGSHUB_TOKEN                                 DagsHub personal access token

Token fallback: a Prefect Secret block named "dagshub-token" (created via
`prefect block create secret` or the Cloud UI).

Env var names mirror the backend .env. URI values are the same connection
strings used across the platform's services.
"""
from __future__ import annotations

import os

from prefect.blocks.system import Secret

DAGSHUB_REPO = os.getenv("DAGSHUB_REPO", "ai-civic-issue-monitoring")
DAGSHUB_USER = os.getenv("DAGSHUB_USERNAME", "")
MLFLOW_BASE = f"https://dagshub.com/{DAGSHUB_USER}/{DAGSHUB_REPO}.mlflow/api/2.0/mlflow"


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name!r}. "
            "Set it on the worker (or in .env) before running flows."
        )
    return value


def get_db_uri() -> str:
    return os.getenv("CIVICPULSE_DB_URI") or os.getenv("DATABASE_URL") or _require("CIVICPULSE_DB_URI")


def get_mongo_uri() -> str:
    return (
        os.getenv("CIVICPULSE_MONGO_URI")
        or os.getenv("MONGODB_URI")
        or _require("CIVICPULSE_MONGO_URI")
    )


def get_dagshub_token() -> str:
    token = os.getenv("DAGSHUB_TOKEN")
    if token:
        return token
    return Secret.load("dagshub-token").get()
