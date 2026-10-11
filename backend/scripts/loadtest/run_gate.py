"""Assert Locust CSV results against P95 / error-rate budgets (CI load gate).

Locust has no built-in "fail when thresholds are exceeded" — a headless run
always exits 0. This script is that gate: it parses the CSV a headless run
writes (``--csv PREFIX`` → ``<PREFIX>_stats.csv``) and exits non-zero when a
budget is breached.

Budgets (env-overridable, float):

* ``LOADTEST_MAX_ERROR_PCT`` — max failure share across ALL request types
  (default ``1.0`` → 1%).
* ``LOADTEST_P95_HEALTH_MS`` — P95 budget for ``/health`` probes
  (default ``500`` ms).
* ``LOADTEST_P95_API_MS``    — P95 budget for every other (authenticated) request
  type (default ``1000`` ms).

Usage (from ``backend/``):

    python scripts/loadtest/run_gate.py --csv loadtest_results_stats.csv

Exit codes: 0 green, 1 budget breached, 2 unusable CSV (missing/empty).
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Final

MAX_ERROR_PCT: Final = float(os.getenv("LOADTEST_MAX_ERROR_PCT", "1.0"))
P95_HEALTH_MS: Final = float(os.getenv("LOADTEST_P95_HEALTH_MS", "500"))
P95_API_MS: Final = float(os.getenv("LOADTEST_P95_API_MS", "1000"))


def _rows(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _p95(row: dict) -> float:
    """The 95th-percentile latency column, whatever Locust names it."""
    for key in ("95%", "95"):
        raw = row.get(key)
        if raw not in (None, ""):
            return float(raw)
    # Header may be e.g. "95%" under a `Name`-less reader; be explicit.
    return float(row.get("95%") or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", required=True, help="path to <prefix>_stats.csv")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.csv):
        print(f"[gate] stats CSV not found: {args.csv}", file=sys.stderr)
        return 2
    rows = _rows(args.csv)
    if not rows:
        print(f"[gate] stats CSV is empty: {args.csv}", file=sys.stderr)
        return 2

    total_requests = 0
    total_failures = 0
    breaches: list[str] = []

    for row in rows:
        name = (row.get("Name") or "").strip()
        req_type = (row.get("Type") or "").strip()
        request_count = int(row.get("Request Count") or 0)
        failure_count = int(row.get("Failure Count") or 0)

        # Locust emits an "Aggregated" summary row in some versions; it is a
        # re-statement of the per-type rows, so counting it twice would skew
        # the global error share. Skip it; per-type rows carry the numbers.
        if req_type.lower() == "aggregated" or name.lower() == "aggregated":
            continue

        total_requests += request_count
        total_failures += failure_count

        error_pct = (failure_count / request_count * 100) if request_count else 0.0
        p95 = _p95(row)
        budget = P95_HEALTH_MS if "/health" in name else P95_API_MS
        if p95 > budget:
            breaches.append(
                f"{name}: P95 {p95:.0f}ms > budget {budget:.0f}ms ({request_count} requests, {error_pct:.2f}% errors)"
            )

    global_error_pct = (total_failures / total_requests * 100) if total_requests else 0.0
    if global_error_pct > MAX_ERROR_PCT:
        breaches.append(
            f"GLOBAL ERROR RATE {global_error_pct:.2f}% > budget {MAX_ERROR_PCT:.2f}% "
            f"({total_failures}/{total_requests} requests)"
        )

    print(f"[gate] requests={total_requests} failures={total_failures} "
          f"error%={global_error_pct:.2f} p95_health_budget={P95_HEALTH_MS:.0f}ms "
          f"p95_api_budget={P95_API_MS:.0f}ms")
    if breaches:
        print("[gate] BUDGET BREACHED:", file=sys.stderr)
        for b in breaches:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print("[gate] OK — all budgets met.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())