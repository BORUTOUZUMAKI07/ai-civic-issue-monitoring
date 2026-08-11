"""One-time data hygiene for data/raw (train/val/test splits).

Fixes three defects found in the Roboflow export (verified by content hash):

  1. Cross-split leakage: the same image content appears in both train and
     test (or val and train). The held-out copy is quarantined so every
     split sees unique content.
  2. Label conflicts: the same image content is labeled with 2+ classes.
     These groups are quarantined entirely (the true label is unknown).
  3. Redundant copies: identical files in the same split are reduced to a
     single copy.

Quarantined files are MOVED to data/_quarantine/<reason>/<split>/<class>/
(no data is deleted) and a report is written to data/_quarantine/report.json.

Run once from the repo root:
    python -m src.ml.training.clean_data
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

DATA_PATH = Path("data/raw")
QUARANTINE = Path("data/_quarantine")
SPLITS = ("train", "val", "test")
CLASSES = ("debris", "garbage", "non_civic", "pothole")
HASH_CHUNK = 1 << 20


def file_hash(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def count_split() -> dict[str, dict[str, int]]:
    counts = {}
    for split in SPLITS:
        counts[split] = {}
        for cls in CLASSES:
            d = DATA_PATH / split / cls
            counts[split][cls] = len(list(d.glob("*"))) if d.exists() else 0
    return counts


def move(member: dict, reason: str, report: list[dict]) -> None:
    dest_dir = QUARANTINE / reason / member["split"] / member["cls"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / member["path"].name
    shutil.move(str(member["path"]), str(dest))
    report.append(
        {"split": member["split"], "cls": member["cls"], "name": member["path"].name, "reason": reason}
    )


def main() -> None:
    if not DATA_PATH.exists():
        print(f"Data path not found: {DATA_PATH}")
        sys.exit(1)

    before = count_split()

    groups: dict[str, list[dict]] = defaultdict(list)
    for split in SPLITS:
        for cls in CLASSES:
            d = DATA_PATH / split / cls
            if not d.exists():
                continue
            for f in d.iterdir():
                if f.is_file():
                    groups[file_hash(f)].append(
                        {"split": split, "cls": cls, "path": f}
                    )

    report: list[dict] = []
    conflict_groups = 0
    leak_test = 0
    leak_val = 0
    dupe = 0

    for members in groups.values():
        if len(members) < 2:
            continue

        classes = sorted({m["cls"] for m in members})

        if len(classes) > 1:
            for m in members:
                move(m, "conflict", report)
            conflict_groups += 1
            continue

        remaining = list(members)

        if "test" in {m["split"] for m in remaining} and len(
            {m["split"] for m in remaining}
        ) > 1:
            for m in remaining:
                if m["split"] == "test":
                    move(m, "leak_test", report)
                    leak_test += 1
            remaining = [m for m in remaining if m["split"] != "test"]

        if "val" in {m["split"] for m in remaining} and "train" in {
            m["split"] for m in remaining
        }:
            for m in remaining:
                if m["split"] == "val":
                    move(m, "leak_val", report)
                    leak_val += 1
            remaining = [m for m in remaining if m["split"] != "val"]

        seen_splits: set[str] = set()
        for m in remaining:
            if m["split"] in seen_splits:
                move(m, "dupe", report)
                dupe += 1
            else:
                seen_splits.add(m["split"])

    after = count_split()
    summary = {
        "conflict_groups_removed": conflict_groups,
        "test_leaks_removed": leak_test,
        "val_leaks_removed": leak_val,
        "redundant_copies_removed": dupe,
        "files_moved_total": len(report),
        "before": before,
        "after": after,
    }

    QUARANTINE.mkdir(parents=True, exist_ok=True)
    (QUARANTINE / "report.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (QUARANTINE / "moved_files.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("=== Before ===")
    for split, cls_count in before.items():
        print(f"  {split}: {cls_count}")
    print("=== After ===")
    for split, cls_count in after.items():
        print(f"  {split}: {cls_count}")
    print("=== Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
