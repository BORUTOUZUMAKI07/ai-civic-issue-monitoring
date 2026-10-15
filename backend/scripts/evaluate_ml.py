#!/usr/bin/env python3
"""Offline evaluation harness for the civic-issue ML stack.

Two independent evaluations, either or both per invocation:

* **classifier** (default, fully offline + deterministic) — scores the keyword
  classifier the agent falls back on against ``data/eval/classifier_golden.json``
  and reports accuracy, per-class precision/recall/F1, macro-F1 and the
  severity mean-absolute-error. ``--mongo`` widens the ground truth with
  human-labelled ``rejected_uploads`` documents (old 7-class labels folded into
  the current 3-class taxonomy; labels with no taxonomy home are dropped).

* **retrieval** (``--retrieval``, needs a populated DB) — runs the golden
  queries through ``find_similar_issues`` and reports MRR / nDCG@k / precision@k
  where a retrieved issue is relevant when its ``issue_type`` matches the probe.
  ``--hybrid`` re-runs with ``RETRIEVAL_HYBRID`` forced on so the two modes can
  be compared in one command. Skips cleanly (exit 0) when no embeddings exist.

The classifier gate fails the process when macro-F1 drops below
``--min-macro-f1`` (default 0.9) unless ``--report-only`` is given, so CI turns
red on an accidental keyword regression but never on an unavailable database.

Usage::

    cd backend
    python scripts/evaluate_ml.py                       # classifier only
    python scripts/evaluate_ml.py --mongo               # + real reviewed data
    python scripts/evaluate_ml.py --retrieval --hybrid  # retrieval, both modes
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.evaluation import metrics  # noqa: E402

import src.models  # noqa: E402, F401 — register every ORM model on Base.metadata

EVAL_DIR = PROJECT_ROOT / "data" / "eval"
CLASSIFIER_GOLDEN = EVAL_DIR / "classifier_golden.json"
RETRIEVAL_GOLDEN = EVAL_DIR / "retrieval_golden.json"

TAXONOMY = ("pothole", "garbage", "debris")

# Old 7-class review labels -> current 3-class taxonomy. Anything absent here
# (broken_streetlight, waterlogging, sewage) has no home in the product's enum
# and is intentionally excluded rather than force-fit.
LEGACY_LABEL_MAP = {
    "pothole": "pothole",
    "road_damage": "pothole",
    "garbage": "garbage",
    "trash": "garbage",
    "debris": "debris",
    "construction": "debris",
    "illegal_construction": "debris",
}


# ─────────────────────────────────────────────────────────────────────────────
# Classifier evaluation
# ─────────────────────────────────────────────────────────────────────────────

def _load_golden(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Golden file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    if not cases:
        raise SystemExit(f"Golden file has no cases: {path}")
    return cases


def _load_mongo_cases() -> list[dict]:
    """Human-labelled rejected uploads, folded into the taxonomy.

    Best-effort: a missing Mongo, missing config, or empty collection returns
    ``[]`` so the offline golden set still runs.
    """
    try:
        from pymongo import MongoClient

        from src.core.config import settings

        client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
        col = client[settings.MONGODB_DB]["rejected_uploads"]
        cases: list[dict] = []
        for doc in col.find({"human_label": {"$ne": None}}):
            mapped = LEGACY_LABEL_MAP.get(str(doc.get("human_label", "")).strip().lower())
            description = (doc.get("description") or "").strip()
            if mapped and description:
                cases.append({"text": description, "category": mapped, "severity": None})
        client.close()
        return cases
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"  (mongo ground truth unavailable, skipping: {exc})")
        return []


def evaluate_classifier(args: argparse.Namespace) -> dict:
    from src.agents.classifier import _keyword_classify

    cases = _load_golden(CLASSIFIER_GOLDEN)
    if args.mongo:
        mongo_cases = _load_mongo_cases()
        print(f"  + {len(mongo_cases)} human-labelled cases from Mongo")
        cases = cases + mongo_cases

    y_true: list[str] = []
    y_pred: list[str] = []
    sev_true: list[int | None] = []
    sev_pred: list[int | None] = []
    for case in cases:
        category, severity, _confidence = _keyword_classify(case["text"])
        y_true.append(case["category"])
        y_pred.append(category)
        sev_true.append(case.get("severity"))
        sev_pred.append(severity)

    report = {
        "cases": len(cases),
        "accuracy": metrics.accuracy(y_true, y_pred),
        "macro_f1": metrics.macro_f1(y_true, y_pred, TAXONOMY),
        "per_class": metrics.per_class_prf(y_true, y_pred, TAXONOMY),
        "severity_mae": metrics.mean_absolute_error(sev_true, sev_pred),
    }

    print(f"\nClassifier — {report['cases']} cases")
    print(f"  accuracy : {report['accuracy']:.3f}")
    print(f"  macro-F1 : {report['macro_f1']:.3f}")
    print(f"  severity MAE: {report['severity_mae']:.3f}")
    for label in TAXONOMY:
        m = report["per_class"][label]
        print(
            f"    {label:<8} P={m['precision']:.2f} R={m['recall']:.2f} "
            f"F1={m['f1']:.2f} n={m['support']}"
        )
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval evaluation
# ─────────────────────────────────────────────────────────────────────────────

async def _retrieval_available() -> tuple[bool, str]:
    """True when the DB has embedded issues AND the embedder answers."""
    from sqlalchemy import func, select

    from src.core.database import AsyncSessionLocal
    from src.core.embeddings import generate_embedding
    from src.domains.issues.models.issue import Issue

    try:
        async with AsyncSessionLocal() as db:
            total = await db.scalar(
                select(func.count()).select_from(Issue).where(Issue.embedding.isnot(None))
            )
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, f"database unavailable ({exc})"
    if not total:
        return False, "no issues with embeddings"

    probe = await generate_embedding("pothole")
    if probe is None:
        return False, "embedding provider unavailable (no HF_TOKEN / network)"
    return True, f"{total} embedded issues"


async def evaluate_retrieval(top_k: int) -> dict:
    from src.core.database import AsyncSessionLocal
    from src.rag.retrieval import find_similar_issues

    cases = _load_golden(RETRIEVAL_GOLDEN)

    mrrs: list[float] = []
    ndcgs: list[float] = []
    precisions: list[float] = []
    async with AsyncSessionLocal() as db:
        for case in cases:
            results = await find_similar_issues(db, case["query"], top_k=top_k)
            relevant = [r["issue_type"] == case["relevant_type"] for r in results]
            mrrs.append(metrics.reciprocal_rank(relevant))
            ndcgs.append(metrics.ndcg_at_k(relevant, top_k))
            precisions.append(metrics.precision_at_k(relevant, top_k))

    def _mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    return {
        "cases": len(cases),
        "top_k": top_k,
        "mrr": _mean(mrrs),
        "ndcg": _mean(ndcgs),
        "precision": _mean(precisions),
    }


def _print_retrieval(label: str, report: dict) -> None:
    print(f"\nRetrieval ({label}) — {report['cases']} queries, top_k={report['top_k']}")
    print(f"  MRR        : {report['mrr']:.3f}")
    print(f"  nDCG@{report['top_k']}   : {report['ndcg']:.3f}")
    print(f"  P@{report['top_k']}      : {report['precision']:.3f}")


async def run_retrieval(args: argparse.Namespace) -> dict:
    ok, reason = await _retrieval_available()
    if not ok:
        print(f"\nRetrieval — SKIPPED ({reason})")
        return {"skipped": True, "reason": reason}

    from src.core.config import settings

    reports: dict = {}
    settings.RETRIEVAL_HYBRID = False
    reports["vector"] = await evaluate_retrieval(args.top_k)
    _print_retrieval("vector", reports["vector"])

    if args.hybrid:
        settings.RETRIEVAL_HYBRID = True
        reports["hybrid"] = await evaluate_retrieval(args.top_k)
        _print_retrieval("hybrid (BM25 + RRF)", reports["hybrid"])
    return reports


# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the civic-issue ML stack")
    parser.add_argument("--classifier", action="store_true", help="classifier eval (default when neither flag given)")
    parser.add_argument("--retrieval", action="store_true", help="retrieval eval (needs a populated DB)")
    parser.add_argument("--mongo", action="store_true", help="augment classifier ground truth from Mongo")
    parser.add_argument("--hybrid", action="store_true", help="also evaluate hybrid retrieval")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-macro-f1", type=float, default=0.9, help="CI gate for the classifier")
    parser.add_argument("--report-only", action="store_true", help="never fail on the classifier threshold")
    parser.add_argument("--json", type=Path, default=None, help="write the full report as JSON to this path")
    args = parser.parse_args()

    run_classifier = args.classifier or not args.retrieval
    report: dict = {}

    if run_classifier:
        report["classifier"] = evaluate_classifier(args)
    if args.retrieval:
        report["retrieval"] = asyncio.run(run_retrieval(args))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")

    if run_classifier and not args.report_only:
        f1 = report["classifier"]["macro_f1"]
        if f1 < args.min_macro_f1:
            print(
                f"\nFAIL: classifier macro-F1 {f1:.3f} < threshold {args.min_macro_f1:.3f}"
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
