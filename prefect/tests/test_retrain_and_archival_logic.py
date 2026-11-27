"""Pure/deterministic tests for retrain dispatch, registration and archival.

These run in the Prefect pixi env (like test_drift_logic.py). No live GitHub,
Prefect Cloud or MongoDB is needed: only the HTTP call and the Mongo client are
stubbed.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "flows"))

import pymongo
import pytest

import audit_log_archival as archival
import retrain_model as retrain


# ── registration gate ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("new_acc", "prev_acc", "expected"),
    [
        (0.91, 0.89, True),  # genuine improvement
        (0.89, 0.89, False),  # no improvement
        (0.80, 0.89, False),  # regression
        (0.91, None, True),  # first usable baseline
        (0.91, 0.0, True),  # old sentinel baseline is not a real score
        (0.0, 0.89, False),  # reported zero is not a usable model
        (0.0, None, False),  # the old bug registered this
        (None, None, False),  # missing metric must never register
        (None, 0.89, False),
        (float("nan"), 0.89, False),
    ],
)
def test_should_register(new_acc, prev_acc, expected) -> None:
    assert retrain.should_register(new_acc, prev_acc) is expected


def test_missing_metric_is_none_not_zero() -> None:
    assert retrain.extract_accuracy({"metrics": []}) is None
    assert retrain.extract_accuracy({"metrics": [{"key": "loss", "value": 0.1}]}) is None
    assert retrain.extract_accuracy({"metrics": [{"key": "best_val_acc", "value": 0.91}]}) == 0.91
    assert retrain.extract_accuracy({"metrics": [{"key": "best_val_acc", "value": None}]}) is None
    assert retrain.extract_accuracy({"metrics": [{"key": "best_val_acc", "value": 0.0}]}) == 0.0


def test_dispatch_uses_github_not_dagsHub(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    class _Response:
        status_code = 204

        def raise_for_status(self) -> None:
            return None

    def _post(url: str, **kwargs: dict) -> _Response:
        calls.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(retrain.requests, "post", _post)

    result = retrain.dispatch_retrain("test-token", 12345, repository="owner/repo")

    assert result == {"status_code": 204, "repository": "owner/repo"}
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "https://api.github.com/repos/owner/repo/dispatches"
    assert kwargs["json"]["event_type"] == "retrain-model"
    assert kwargs["json"]["client_payload"]["trigger_time_ms"] == 12345
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


# ── archival retry safety ────────────────────────────────────────────────────


class _FakeCollection:
    def __init__(self, docs: list[dict] | None = None) -> None:
        # Keep the caller's list by reference so a second MongoClient in the
        # same test sees what the first one wrote.
        self.docs = docs if docs is not None else []

    def find(self, query: dict) -> list[dict]:
        cutoff = query["timestamp"]["$lt"]
        return [dict(doc) for doc in self.docs if doc["timestamp"] < cutoff]

    def bulk_write(self, operations: list, ordered: bool) -> None:
        for op in operations:
            doc = op._doc.get("$setOnInsert", {})
            if not any(existing["_id"] == doc["_id"] for existing in self.docs):
                self.docs.append(dict(doc))

    def delete_many(self, query: dict) -> None:
        ids = set(query["_id"]["$in"])
        self.docs[:] = [doc for doc in self.docs if doc["_id"] not in ids]


class _FakeDB:
    def __init__(self, data: dict[str, list[dict]]) -> None:
        self.data = data

    def __getitem__(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.data.setdefault(name, []))


class _FakeClient:
    def __init__(self, data: dict[str, list[dict]]) -> None:
        self.db = _FakeDB(data)

    def __getitem__(self, name: str) -> _FakeDB:
        assert name == archival.MONGO_DB
        return self.db

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _SilentLogger:
    def info(self, *args: object, **kwargs: object) -> None:
        return None


@pytest.fixture
def _stub_archival(monkeypatch):
    def _install(data: dict[str, list[dict]]) -> None:
        monkeypatch.setattr(pymongo, "MongoClient", lambda *a, **k: _FakeClient(data))
        monkeypatch.setattr(archival, "get_run_logger", lambda: _SilentLogger())

    return _install


def _old_doc(doc_id: int) -> dict:
    return {
        "_id": doc_id,
        "timestamp": datetime.now(timezone.utc) - timedelta(days=120),
        "event": "test",
    }


def test_archival_is_idempotent_on_retry(_stub_archival) -> None:
    # Capture the source doc once: archive_old_logs preserves it verbatim via
    # `$setOnInsert`, so the expected copy must carry the *same* timestamp.
    # Rebuilding `_old_doc(1)` here generated a fresh microsecond value and
    # made this test fail intermittently for reasons unrelated to the flow.
    doc = _old_doc(1)
    data = {"audit_logs": [dict(doc)]}
    _stub_archival(data)

    assert archival.archive_old_logs.fn("mongodb://fake") == 1
    assert archival.archive_old_logs.fn("mongodb://fake") == 0

    assert data["audit_logs"] == []
    assert data["archived_audit_logs"] == [doc]


def test_archival_retry_after_partial_write_does_not_duplicate(_stub_archival) -> None:
    doc = _old_doc(2)
    # Simulate a run that wrote the archive but died before deleting the source.
    data = {"audit_logs": [dict(doc)], "archived_audit_logs": [dict(doc)]}
    _stub_archival(data)

    assert archival.archive_old_logs.fn("mongodb://fake") == 1
    assert data["archived_audit_logs"] == [doc]
    assert data["audit_logs"] == []
