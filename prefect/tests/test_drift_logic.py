"""Unit tests for the pure/deterministic drift-detection logic.

These tests exercise the math (_js_divergence, _entropy) and the severity
classification (detect_drift) WITHOUT requiring a live MongoDB/Prefect Cloud.
They are run against the Prefect venv (see prefect/requirements.txt), not the
backend pixi env, because the module imports prefect.

pymongo.MongoClient is stubbed out so the drift-report write is a no-op.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "flows"))

import pymongo
import pytest

from drift_detection import _entropy, _js_divergence, detect_drift


class _FakeCollection:
    def insert_one(self, doc):
        return doc


class _FakeDB:
    def __getitem__(self, name):
        return _FakeCollection()


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self._db = _FakeDB()

    def __getitem__(self, name):
        return self._db

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _stub_mongo(monkeypatch):
    monkeypatch.setattr(pymongo, "MongoClient", _FakeClient)


class TestJsDivergence:
    def test_identical_distributions_zero(self) -> None:
        p = {"a": 0.5, "b": 0.5}
        assert _js_divergence(p, dict(p)) == pytest.approx(0.0, abs=1e-9)

    def test_js_between_zero_and_ln2(self) -> None:
        p = {"a": 1.0}
        q = {"b": 1.0}
        js = _js_divergence(p, q)
        assert 0.0 < js <= 0.693148  # <= ln(2) ~ 0.69314718
        assert js == pytest.approx(0.693147, abs=1e-3)

    def test_symmetric(self) -> None:
        p = {"a": 0.8, "b": 0.2}
        q = {"a": 0.4, "b": 0.6}
        assert _js_divergence(p, q) == pytest.approx(_js_divergence(q, p), abs=1e-12)

    def test_missing_keys_handled(self) -> None:
        p = {"a": 1.0}
        q = {"a": 0.5, "b": 0.5}
        assert _js_divergence(p, q) >= 0.0


class TestEntropy:
    def test_certainty_zero_entropy(self) -> None:
        assert _entropy({"a": 1.0}) == pytest.approx(0.0)

    def test_uniform_two_classes(self) -> None:
        assert _entropy({"a": 0.5, "b": 0.5}) == pytest.approx(0.693147, abs=1e-3)

    def test_empty_distribution_zero(self) -> None:
        assert _entropy({}) == 0.0

    def test_ignores_zero_probabilities(self) -> None:
        assert _entropy({"a": 1.0, "b": 0.0}) == pytest.approx(0.0)


class TestDetectDriftSeverity:
    def test_low_drift_when_distributions_match(self) -> None:
        baselines = {
            "mean_confidence": 0.9,
            "std_confidence": 0.05,
            "class_distribution": {"pothole": 0.6, "garbage": 0.4},
            "entropy": _entropy({"pothole": 0.6, "garbage": 0.4}),
        }
        # Realistic confidence values with ~0.05 std, and class split ~60/40
        confs = [0.85, 0.87, 0.89, 0.91, 0.93] * 7
        predictions = [{"confidence": c, "predicted_label": "pothole"} for c in confs]
        predictions += [{"confidence": c, "predicted_label": "garbage"} for c in [0.86, 0.88, 0.9, 0.92, 0.94] * 5]
        report = detect_drift("", predictions, baselines)
        assert report is not None
        assert report["severity"] == "low"
        assert report["drift_detected"] is False

    def test_high_drift_on_mean_confidence_shift(self) -> None:
        baselines = {
            "mean_confidence": 0.95,
            "std_confidence": 0.01,
            "class_distribution": {"pothole": 0.5, "garbage": 0.5},
            "entropy": _entropy({"pothole": 0.5, "garbage": 0.5}),
        }
        # Confidence collapsed to 0.5 -> ~47% relative drop -> high
        predictions = [{"confidence": 0.5, "predicted_label": "pothole"} for _ in range(20)]
        predictions += [{"confidence": 0.5, "predicted_label": "garbage"} for _ in range(20)]
        report = detect_drift("", predictions, baselines)
        assert report is not None
        assert report["severity"] == "high"
        assert report["drift_detected"] is True

    def test_zero_predictions_returns_none(self) -> None:
        report = detect_drift(
            "",
            [],
            {"mean_confidence": 0.9, "std_confidence": 0.1, "class_distribution": {}, "entropy": 0},
        )
        assert report is None

    def test_too_few_samples_returns_none(self) -> None:
        report = detect_drift(
            "",
            [{"confidence": 0.9, "predicted_label": "pothole"}],
            {"mean_confidence": 0.9, "std_confidence": 0.1, "class_distribution": {}, "entropy": 0},
        )
        assert report is None

    def test_high_class_divergence_flags_high(self) -> None:
        baselines = {
            "mean_confidence": 0.9,
            "std_confidence": 0.05,
            "class_distribution": {"pothole": 1.0},
            "entropy": 0.0,
        }
        # Completely flipped to garbage in current window -> high JS divergence
        predictions = [{"confidence": 0.9, "predicted_label": "garbage"} for _ in range(20)]
        report = detect_drift("", predictions, baselines)
        assert report is not None
        assert report["severity"] == "high"
