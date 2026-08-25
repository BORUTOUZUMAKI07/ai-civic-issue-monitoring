#!/usr/bin/env python3
"""
Phase 4: Export reviewed uploads with AI pre-sort.

Two-pass process:
  Pass 1 — Admin-labeled photos go straight into class folders.
  Pass 2 — Unlabeled photos get a best-guess from the text classifier,
           sorted into "maybe_{label}/" folders for fast human review.

Usage:
    cd backend
    python scripts/export_reviewed_uploads.py
    python scripts/export_reviewed_uploads.py --dry-run       # preview only
    python scripts/export_reviewed_uploads.py --include-rejected

Output:
    data/reviewed/
      broken_streetlight/       ← admin-labeled, ready for retrain
      maybe_broken_streetlight/ ← AI-guessed, human confirms
      maybe_garbage/
      unsure/                   ← no description, must check manually
"""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "reviewed"

CIVIC_KEYWORDS: dict[str, list[str]] = {
    "pothole": ["pothole", "road damage", "road crack", "broken road"],
    "garbage": ["garbage", "waste", "trash", "rubbish", "dump", "litter"],
    "broken_streetlight": ["streetlight", "street light", "lamp", "no light"],
    "waterlogging": ["waterlogging", "flood", "water", "drainage", "stagnant"],
    "debris": ["debris", "rubble", "construction waste"],
    "sewage": ["sewage", "sewer", "clogged drain", "blocked drain"],
    "road_damage": ["road damage", "road broken", "asphalt", "road repair"],
}


def guess_label_from_description(description: str) -> str | None:
    """Best-guess label from text description using keyword matching."""
    if not description:
        return None

    desc_lower = description.lower()
    best_label = None
    best_score = 0

    for label, keywords in CIVIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in desc_lower)
        if score > best_score:
            best_score = score
            best_label = label

    return best_label if best_score > 0 else None


def copy_image(image_url: str, dest_dir: Path, dry_run: bool) -> bool:
    """Copy image from uploads to dest_dir. Returns True if copied."""
    if not image_url:
        return False

    src = PROJECT_ROOT.parent / image_url.lstrip("/")
    if not src.exists():
        src = PROJECT_ROOT / image_url.lstrip("/")
    if not src.exists():
        return False

    dest = dest_dir / src.name
    if dest.exists():
        return True

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Export and pre-sort reviewed uploads")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--include-rejected", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true", help="Preview without copying files")
    args = parser.parse_args()

    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from pymongo import MongoClient

    from src.core.config import settings

    client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = client[settings.MONGODB_DB]
    col = db["rejected_uploads"]

    query: dict = {}
    if not args.include_rejected:
        query["action_taken"] = "overridden_approved"

    cursor = col.find(query).sort("created_at", -1)
    if args.limit:
        cursor = cursor.limit(args.limit)

    stats: dict[str, int] = {}
    total = 0

    for doc in cursor:
        total += 1
        image_url = doc.get("image_url", "")
        human_label = doc.get("human_label")
        description = doc.get("description", "")

        if human_label:
            # Pass 1: admin already labeled → confirmed class folder
            safe = human_label.replace(" ", "_").lower()
            target = args.output / safe
            copy_image(image_url, target, args.dry_run)
            stats[safe] = stats.get(safe, 0) + 1
        else:
            # Pass 2: no label → AI pre-sort
            guessed = guess_label_from_description(description)
            if guessed:
                target = args.output / f"maybe_{guessed}"
                copy_image(image_url, target, args.dry_run)
                stats[f"maybe_{guessed}"] = stats.get(f"maybe_{guessed}", 0) + 1
            else:
                target = args.output / "unsure"
                copy_image(image_url, target, args.dry_run)
                stats["unsure"] = stats.get("unsure", 0) + 1

    client.close()

    mode = "DRY RUN" if args.dry_run else "EXPORTED"
    logger.info("[%s] %d documents processed → %s", mode, total, args.output)

    confirmed = {k: v for k, v in stats.items() if not k.startswith("maybe_") and k != "unsure"}
    guessed = {k: v for k, v in stats.items() if k.startswith("maybe_")}
    unsure = stats.get("unsure", 0)

    if confirmed:
        logger.info("\nConfirmed (ready for retrain):")
        for k, v in sorted(confirmed.items()):
            logger.info("  %s: %d", k, v)

    if guessed:
        logger.info("\nAI pre-sorted (review to confirm):")
        for k, v in sorted(guessed.items()):
            logger.info("  %s: %d", k, v)

    if unsure:
        logger.info("\nUnsure (no text signal — check manually): %d", unsure)

    logger.info(
        "\nNext step: open '%s' and confirm the maybe_* folders.",
        args.output,
    )


if __name__ == "__main__":
    main()
