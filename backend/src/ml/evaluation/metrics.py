"""Pure evaluation metrics for the civic-issue ML stack.

Deliberately dependency-free and side-effect-free: every function takes plain
sequences and returns numbers, so the harness that computes them and the tests
that verify them both stay honest. No scikit-learn — the metric set here is
small enough that a hidden dependency would cost more than it saves.
"""

from __future__ import annotations

import math
from typing import Any, Sequence


def accuracy(y_true: Sequence[Any], y_pred: Sequence[Any]) -> float:
    if not y_true:
        return 0.0
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return correct / len(y_true)


def per_class_prf(y_true: Sequence[Any], y_pred: Sequence[Any], labels: Sequence[str]) -> dict[str, dict[str, float]]:
    """Precision/recall/F1/support for each label.

    A label with no predicted and no true instances reports zeros (not 1.0) so
    it cannot flatter a macro average; a label that IS present in the truth but
    never predicted gets recall 0 and F1 0, which is the honest signal.
    """
    result: dict[str, dict[str, float]] = {}
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if p == label and t != label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        support = tp + fn
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        result[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
    return result


def macro_f1(y_true: Sequence[Any], y_pred: Sequence[Any], labels: Sequence[str]) -> float:
    if not labels:
        return 0.0
    per = per_class_prf(y_true, y_pred, labels)
    return sum(per[label]["f1"] for label in labels) / len(labels)


def mean_absolute_error(y_true: Sequence[float | None], y_pred: Sequence[float | None]) -> float:
    pairs: list[tuple[float, float]] = [(t, p) for t, p in zip(y_true, y_pred) if t is not None and p is not None]
    if not pairs:
        return 0.0
    return sum(abs(t - p) for t, p in pairs) / len(pairs)


def precision_at_k(ranked_relevant: Sequence[bool], k: int) -> float:
    if k <= 0:
        return 0.0
    top = list(ranked_relevant)[:k]
    if not top:
        return 0.0
    return sum(1 for r in top if r) / len(top)


def reciprocal_rank(ranked_relevant: Sequence[bool]) -> float:
    """1 / rank of the first relevant item (1-based); 0.0 if none."""
    for i, relevant in enumerate(ranked_relevant):
        if relevant:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(ranked_relevant: Sequence[bool], k: int) -> float:
    """Binary-gain nDCG@k. Ideal ranking puts all relevant hits first."""
    top = list(ranked_relevant)[:k]
    if not top:
        return 0.0
    dcg = sum((1.0 if r else 0.0) / math.log2(i + 2) for i, r in enumerate(top))
    ideal_hits = sum(1 for r in ranked_relevant if r)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(ideal_hits, k)))
    return dcg / ideal if ideal else 0.0
