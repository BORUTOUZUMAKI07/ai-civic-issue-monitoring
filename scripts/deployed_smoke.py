"""Post-deploy smoke test for a real CivicPulse installation.

Pure stdlib so it can run on a bare GitHub runner. It exercises the *deployed*
stack through the Next.js BFF — not the backend directly — so it catches proxy
cookie-path mistakes, missing env vars and broken container networking that unit
tests cannot see.

Required env (or flags):
    SMOKE_BASE_URL   public frontend origin, e.g. https://civic.example.com
    SMOKE_EMAIL      seeded test user with a known password
    SMOKE_PASSWORD   that user's password

Optional:
    SMOKE_ADMIN_EMAIL / SMOKE_ADMIN_PASSWORD  enables the admin audit checks
    SMOKE_TIMEOUT    per-request timeout in seconds (default 15)

Nothing is written to the deployment beyond ordinary login/refresh/audit reads.
Exit code is 1 if any check fails.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

PASS = "PASS"
FAIL = "FAIL"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class Smoker:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies), NoRedirect()
        )
        self.failures = 0

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        expected: int | None = 200,
        label: str | None = None,
    ) -> tuple[int, dict[str, str], str]:
        url = f"{self.base}{path}"
        data = None
        headers: dict[str, str] = {"Accept": "application/json, text/html;q=0.9"}
        # The Next.js BFF CSRF guard rejects state-changing requests with no
        # Origin (it fails closed). Browsers always send one; the smoke client
        # must too, or every mutation is refused before reaching the backend.
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            headers["Origin"] = self.base
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        status = 0
        response_headers: dict[str, str] = {}
        body = ""
        try:
            with self.opener.open(req, timeout=self.timeout) as res:
                status = res.status
                response_headers = {k.lower(): v for k, v in res.headers.items()}
                body = res.read(1_000_000).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_headers = {k.lower(): v for k, v in exc.headers.items()}
            body = exc.read(1_000_000).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - report and keep checking
            self._result(False, label or f"{method} {path}", f"request failed: {exc}")
            return status, response_headers, body

        ok = status == expected if expected is not None else status < 400
        detail = "" if ok else f"expected {expected}, got {status}: {body[:200]}"
        self._result(ok, label or f"{method} {path}", detail)
        return status, response_headers, body

    def _result(self, ok: bool, label: str, detail: str = "") -> None:
        print(f"[{PASS if ok else FAIL}] {label}{(': ' + detail) if detail else ''}", flush=True)
        if not ok:
            self.failures += 1

    def json_body(self, body: str) -> dict[str, Any]:
        try:
            parsed = json.loads(body)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}


def run(args: argparse.Namespace) -> int:
    s = Smoker(args.base_url, args.timeout)
    print(f"Smoke target: {s.base}", flush=True)

    # 1. Frontend actually serves the app.
    status, _, body = s.request("GET", "/", expected=200, label="frontend homepage")
    if status == 200 and "<html" not in body.lower():
        s._result(False, "frontend homepage", "response is not HTML")

    # 2. BFF forwards to the backend on a public route.
    _, _, body = s.request(
        "GET", "/api/proxy/auth/oauth/providers", label="BFF -> backend (providers)"
    )
    providers = s.json_body(body)
    s._result(
        isinstance(providers.get("google"), bool) and isinstance(providers.get("github"), bool),
        "providers payload shape",
        "" if providers else "unexpected response",
    )
    s.request(
        "POST",
        "/api/proxy/auth/oauth/exchange",
        payload={"code": "x" * 43},
        expected=401,
        label="OAuth handoff replay rejected",
    )

    # 3. Login / session / refresh through the proxy cookie boundary.
    s.cookies.clear()
    s.request(
        "POST",
        "/api/proxy/auth/login",
        payload={"email": args.email, "password": args.password},
        label="login",
    )
    _, _, me_body = s.request("GET", "/api/proxy/auth/me", label="authenticated /auth/me")
    me = s.json_body(me_body)
    s._result(str(me.get("email", "")).lower() == args.email.lower(), "session identity", str(me.get("email")))
    s.request("POST", "/api/proxy/auth/refresh", label="refresh rotates session")

    # 4. Optional admin/compliance surface. Log in with a separate cookie jar so
    #    the smoke user's session stays intact. Both credentials are required;
    #    a half-configured pair is skipped rather than crashing on `admin`.
    admin_failures = 0
    if args.admin_email and args.admin_password:
        admin = Smoker(args.base_url, args.timeout)
        admin.cookies.clear()
        admin.request(
            "POST",
            "/api/proxy/auth/login",
            payload={"email": args.admin_email, "password": args.admin_password},
            label="admin login",
        )
        admin.request(
            "GET", "/api/proxy/admin/audit/report?days=1", label="admin audit report via BFF"
        )
        admin.request(
            "GET", "/api/proxy/admin/audit/events?limit=5", label="admin audit events via BFF"
        )
        admin.request(
            "GET", "/api/proxy/admin/audit/export.csv", label="admin audit CSV export via BFF"
        )
        admin_failures = admin.failures

    total = s.failures + admin_failures
    print(f"\nSmoke result: {'PASS' if total == 0 else 'FAIL'} ({total} failure(s))", flush=True)
    return 1 if total else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("SMOKE_BASE_URL", ""))
    parser.add_argument("--email", default=os.environ.get("SMOKE_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("SMOKE_PASSWORD", ""))
    parser.add_argument("--admin-email", default=os.environ.get("SMOKE_ADMIN_EMAIL", ""))
    parser.add_argument("--admin-password", default=os.environ.get("SMOKE_ADMIN_PASSWORD", ""))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("SMOKE_TIMEOUT", "15")))
    args = parser.parse_args()

    missing = [name for name, value in (("SMOKE_BASE_URL", args.base_url), ("SMOKE_EMAIL", args.email), ("SMOKE_PASSWORD", args.password)) if not value]
    if missing:
        print(f"Missing required smoke inputs: {', '.join(missing)}", file=sys.stderr)
        return 2
    parsed = urllib.parse.urlparse(args.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        print("SMOKE_BASE_URL must be an absolute http(s) URL", file=sys.stderr)
        return 2
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
