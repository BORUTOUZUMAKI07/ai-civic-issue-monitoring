"""Guard the issue-type taxonomy across every layer that has to agree.

Three categories are canonical -- they are the DB enum after migration 005:

    pothole, garbage, debris

The trained model has a fourth output, ``non_civic``, which is a *reject*
class: it is real, it is emitted, and it deliberately has no DB
representation. The intake gate must never let it become an issue type, and
nothing downstream may silently coerce an unknown label into ``pothole``.

Layers checked here:
    src/models/issue.py        IssueType enum (DB)
    src/core/gate.py           CIVIC_LABELS + keyword fallback classifier
    src/domains/issues/...     label -> IssueType mapping
    configs/class_names.json   trained model class list
    data/seed/issues.json      generated seed rows
"""
from __future__ import annotations

import json
from pathlib import Path

from src.core.gate import (
    CIVIC_KEYWORDS,
    CIVIC_LABELS,
    classify_description,
    gate_decision,
)
from src.models.issue import ISSUE_TYPE_MAP, IssueType

BACKEND_DIR = Path(__file__).resolve().parents[1]
CANONICAL = {"pothole", "garbage", "debris"}
REJECT_CLASS = "non_civic"
REMOVED = {"road_damage", "sewage", "broken_streetlight", "waterlogging"}


def _model_classes() -> list[str]:
    path = BACKEND_DIR / "configs" / "class_names.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_db_enum_is_the_canonical_three() -> None:
    assert {t.value for t in IssueType} == CANONICAL
    assert set(ISSUE_TYPE_MAP) == CANONICAL


def test_gate_labels_match_db_enum() -> None:
    # The keyword fallback picks the category when vision is unavailable, so a
    # mismatch here would file issues under a type the DB cannot store.
    assert CIVIC_LABELS == CANONICAL
    assert set(CIVIC_KEYWORDS) == CANONICAL


def test_model_classes_are_canonical_plus_reject_class() -> None:
    assert set(_model_classes()) == CANONICAL | {REJECT_CLASS}


def test_keyword_classifier_only_emits_canonical_labels() -> None:
    samples = [
        "pothole on the main road",
        "pile of garbage",
        "construction debris",
        "broken streetlight near the school",  # removed category
        "sewage overflow",  # removed category
        "",  # no description at all
    ]
    for text in samples:
        assert classify_description(text)["label"] in CANONICAL, text


def test_force_submit_never_returns_the_reject_class() -> None:
    # force_submit falls back to the vision label, which may legitimately be
    # `non_civic` -- that must not leak through as an issue type.
    vision = {
        "label": REJECT_CLASS,
        "confidence": 0.4,
        "is_civic": False,
        "is_non_civic": True,
        "civic_prob": 0.4,
    }
    decision = gate_decision(vision, "", force_submit=True)
    assert decision["action"] == "accept"
    assert decision["issue_type"] in CANONICAL


def test_unknown_vision_label_falls_back_to_a_real_category() -> None:
    vision = {"label": "road_damage", "confidence": 0.9, "is_civic": True}
    decision = gate_decision(vision, "", force_submit=True)
    assert decision["issue_type"] in CANONICAL


def test_seed_rows_only_use_canonical_types() -> None:
    path = BACKEND_DIR / "data" / "seed" / "issues.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert rows, "seed file is empty"
    found = {row["issue_type"] for row in rows}
    assert found <= CANONICAL, f"seed data has removed types: {found - CANONICAL}"


def test_removed_types_are_absent_from_the_lookup_layer() -> None:
    assert REMOVED & set(ISSUE_TYPE_MAP) == set()
    assert REMOVED & CIVIC_LABELS == set()
