"""Deployed smoke client must emulate a browser's CSRF Origin header.

The Next.js BFF fails closed on mutations without an ``Origin`` matching the
request host. A real browser always sends it; a bare urllib client does not, so
without this every smoke mutation is rejected with 403 before it reaches the
backend. These tests pin that boundary without contacting a deployment.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "deployed_smoke.py"

_spec = importlib.util.spec_from_file_location("deployed_smoke", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
deployed_smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deployed_smoke)


class _FakeResponse:
    status = 200
    headers: dict[str, str] = {}

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return b"{}"


class _CapturingOpener:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    def open(self, request: Any, timeout: float) -> _FakeResponse:
        self.requests.append(request)
        return _FakeResponse()


def _smoker_with_capture() -> tuple[Any, _CapturingOpener]:
    smoker = deployed_smoke.Smoker("https://app.example", 5)
    opener = _CapturingOpener()
    smoker.opener = opener
    return smoker, opener


def test_mutations_send_the_canonical_origin() -> None:
    """POSTs carry an Origin the BFF CSRF guard accepts as same-origin."""
    smoker, opener = _smoker_with_capture()

    status, _, _ = smoker.request(
        "POST", "/api/proxy/auth/login", payload={"email": "a@example.com", "password": "x"}
    )

    assert status == 200
    assert opener.requests[0].get_header("Origin") == "https://app.example"


def test_reads_do_not_send_an_origin() -> None:
    """The Origin is scoped to state-changing methods, like a browser sends it."""
    smoker, opener = _smoker_with_capture()

    smoker.request("GET", "/api/proxy/auth/me")

    assert opener.requests[0].get_header("Origin") is None
