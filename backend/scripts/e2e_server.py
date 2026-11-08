"""Boot a backend instance suitable for end-to-end / Playwright runs.

Used by CI and local developers to spin up a real backend (with a seeded
admin account) that the frontend E2E suite can talk to through /api/proxy.
Defaults to a throw-away SQLite database so no Postgres is required.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "e2e-secret-key-not-for-production-32chars")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{ROOT / 'e2e.db'}")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGODB_URI", "")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("ADMIN_EMAIL", "e2e@test.com")
os.environ.setdefault("ADMIN_PASSWORD", "E2ePass1234!")
os.environ.setdefault("ADMIN_FULL_NAME", "E2E Admin")
os.environ.setdefault("ADMIN_ROLE", "super_admin")

db_path = ROOT / "e2e.db"
if db_path.exists():
    try:
        db_path.unlink()
    except OSError:
        pass

# Seed the first admin (creates tables via init_db in non-production).
spec = importlib.util.spec_from_file_location("create_admin", ROOT / "scripts" / "create_admin.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
import asyncio

rc = asyncio.run(mod.main())
if rc != 0:
    raise SystemExit(rc)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, log_level="info")
