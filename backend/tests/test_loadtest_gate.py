"""Budget gate behaviour for the headless Locust run.

The CI load job disables Locust's default "any failure exits 1" so this
stdlib-only parser is the single pass/fail decision point. These tests keep
that authority honest: it must accept normal noise, reject real breaches, and
fail closed when the CSV cannot prove any traffic happened.
"""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "loadtest" / "run_gate.py"


@pytest.fixture()
def gate(monkeypatch: pytest.MonkeyPatch) -> Any:
    spec = importlib.util.spec_from_file_location("run_gate_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Budgets are read from the environment at import time, so pin them here
    # regardless of whichever env happens to run the suite.
    monkeypatch.setattr(module, "MAX_ERROR_PCT", 1.0)
    monkeypatch.setattr(module, "P95_HEALTH_MS", 500.0)
    monkeypatch.setattr(module, "P95_API_MS", 1000.0)
    return module


def _stats_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Type", "Name", "Request Count", "Failure Count", "95%"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_gate_accepts_budgets_with_normal_transient_noise(gate: Any, tmp_path: Path) -> None:
    csv_path = _stats_csv(
        tmp_path / "stats.csv",
        [
            {"Type": "GET", "Name": "GET /health", "Request Count": 1000, "Failure Count": 1, "95%": 100},
            {"Type": "GET", "Name": "GET /issues", "Request Count": 100, "Failure Count": 0, "95%": 200},
        ],
    )
    assert gate.main(["--csv", str(csv_path)]) == 0


def test_gate_rejects_error_rate_above_budget(gate: Any, tmp_path: Path) -> None:
    csv_path = _stats_csv(
        tmp_path / "stats.csv",
        [{"Type": "GET", "Name": "GET /health", "Request Count": 100, "Failure Count": 2, "95%": 100}],
    )
    assert gate.main(["--csv", str(csv_path)]) == 1


def test_gate_rejects_p95_above_budget(gate: Any, tmp_path: Path) -> None:
    csv_path = _stats_csv(
        tmp_path / "stats.csv",
        [{"Type": "GET", "Name": "GET /health", "Request Count": 100, "Failure Count": 0, "95%": 600}],
    )
    assert gate.main(["--csv", str(csv_path)]) == 1


def test_gate_fails_closed_on_aggregated_only_csv(gate: Any, tmp_path: Path) -> None:
    csv_path = _stats_csv(
        tmp_path / "stats.csv",
        [{"Type": "Aggregated", "Name": "Aggregated", "Request Count": 1000, "Failure Count": 0, "95%": 1}],
    )
    assert gate.main(["--csv", str(csv_path)]) == 2
