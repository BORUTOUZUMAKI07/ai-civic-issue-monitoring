"""Locust load-test suite for the CivicPulse API.

A smoke-scale workload for the read paths a deployment actually serves — the
health probe, the issues list, dashboard stats and a search — plus an opt-in
upload task. It is deliberately NOT part of the default pixi environment
(locust drags in gevent/msgpack/pyzmq); install the ``loadtest`` feature:

    pixi run -e loadtest -- loadtest --host https://api.example.com

Configuration (environment variables):

* ``LOCUST_EMAIL`` / ``LOCUST_PASSWORD`` — a real account. Without them the
  authenticated tasks are skipped and only ``/health`` is exercised.
* ``LOCUST_API_PREFIX`` — defaults to ``/api/v1``.
* ``LOCUST_UPLOAD`` — set to ``true`` to enable the (side-effectful) upload
  task. Off by default so a load run does not litter the database with issues.

Note on cookies: ``POST /auth/login`` authenticates by setting httpOnly
cookies, which Locust's ``HttpSession`` retains. Against an ``https`` host the
``Secure`` cookie flows normally; against plain ``http`` the browser-equivalent
rules mean the cookie is not sent — point the run at https (or a reverse proxy
that terminates TLS) for the authenticated tasks to register.
"""
from __future__ import annotations

import base64
import os
import time

from locust import HttpUser, between, events, task

API_PREFIX = os.getenv("LOCUST_API_PREFIX", "/api/v1")
ENABLE_UPLOAD = os.getenv("LOCUST_UPLOAD", "").lower() in ("1", "true", "yes")

# Smallest valid PNG (1x1, transparent) so the upload task passes image
# validation without shipping a binary fixture.
_ONE_PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


class CivicPulseUser(HttpUser):
    """A signed-in reporter browsing the app, with occasional uploads."""

    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.authed = False
        email = os.getenv("LOCUST_EMAIL")
        password = os.getenv("LOCUST_PASSWORD")
        if not email or not password:
            return
        with self.client.post(
            f"{API_PREFIX}/auth/login",
            json={"email": email, "password": password},
            catch_response=True,
            name="POST /auth/login",
        ) as resp:
            if resp.status_code == 200:
                self.authed = True
                resp.success()
            else:
                resp.failure(f"login failed: {resp.status_code}")

    @task(6)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")

    @task(4)
    def list_issues(self) -> None:
        if not self.authed:
            return
        self.client.get(f"{API_PREFIX}/issues?skip=0&limit=20", name="GET /issues")

    @task(2)
    def dashboard_stats(self) -> None:
        if not self.authed:
            return
        self.client.get(f"{API_PREFIX}/dashboard/stats", name="GET /dashboard/stats")

    @task(2)
    def dashboard_heatmap(self) -> None:
        if not self.authed:
            return
        self.client.get(f"{API_PREFIX}/dashboard/heatmap", name="GET /dashboard/heatmap")

    @task(1)
    def search_issues(self) -> None:
        if not self.authed:
            return
        self.client.get(f"{API_PREFIX}/issues/search?q=pothole", name="GET /issues/search")

    @task(1)
    def upload_issue(self) -> None:
        if not (self.authed and ENABLE_UPLOAD):
            return
        files = {"file": ("loadtest.png", _ONE_PX_PNG, "image/png")}
        data = {
            "latitude": "22.3072",
            "longitude": "73.1812",
            "description": "load test pothole on the main road",
            "force_submit": "false",
        }
        # A per-request idempotency key keeps retries of a single logical upload
        # from creating duplicates under load, mirroring the real client.
        headers = {"Idempotency-Key": f"loadtest-{os.getpid()}-{time.time_ns()}"}
        self.client.post(
            f"{API_PREFIX}/issues/upload",
            files=files,
            data=data,
            headers=headers,
            name="POST /issues/upload",
        )


@events.test_start.add_listener
def _warn_without_credentials(environment, **_kwargs) -> None:
    if not (os.getenv("LOCUST_EMAIL") and os.getenv("LOCUST_PASSWORD")):
        print(
            "[loadtest] LOCUST_EMAIL/LOCUST_PASSWORD not set — "
            "authenticated tasks will be skipped; only /health is exercised."
        )
