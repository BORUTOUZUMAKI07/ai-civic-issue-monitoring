"""Load prefect/.env into the environment (for local flow runs / testing).

Loads plain KEY=VALUE lines (ignores comments and blank lines). Values may
optionally be quoted. Does NOT override variables already set in os.environ so
that CI/worker-injected env vars always win.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_prefect_env(path: str | os.PathLike = "prefect/.env") -> None:
    env_file = Path(path)
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


if __name__ == "__main__":
    load_prefect_env()
    for k in (
        "CIVICPULSE_DB_URI",
        "CIVICPULSE_MONGO_URI",
        "DAGSHUB_TOKEN",
        "DAGSHUB_USERNAME",
        "DAGSHUB_REPO",
        "MLFLOW_TRACKING_URI",
    ):
        v = os.getenv(k, "")
        masked = v if not v else (v[:14] + f"...({len(v)} chars)")
        print(f"{k} = {masked}")
