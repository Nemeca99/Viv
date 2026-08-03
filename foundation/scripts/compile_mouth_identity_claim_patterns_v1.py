#!/usr/bin/env python3
"""Compile identity-claim evidence across the current semantic packs.

This report is diagnostic only.  It does not admit data, authorize training,
or alter any source pack.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.evaluator_v2_3_hybrid import judge

POSITIVE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42/semantic_refinement_96_hold.jsonl"
NEGATIVE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_adversarial/semantic_adversarial_48_judge_only.jsonl"
OUTPUT = POSITIVE.parent / "IDENTITY_CLAIM_PATTERN_REPORT_V1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path, split: str) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            row["_split"] = split
            rows.append(row)
    return rows


def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUTPUT}")
    rows = read_rows(POSITIVE, "positive") + read_rows(NEGATIVE, "negative")
    by_category = Counter()
    by_split = Counter()
    by_axis = Counter()
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    status_counts = Counter()
    for row in rows:
        result = judge(row["target"], axis=row["axis"], ask=row.get("ask", ""))
        status_counts[f"{row['_split']}:{result['status']}"] += 1
        for claim in result["deterministic"]["identity_claims"]:
            category = claim["category"]
            by_category[category] += 1
            by_split[f"{row['_split']}:{category}"] += 1
            by_axis[f"{row['axis']}:{category}"] += 1
            if len(examples[category]) < 5:
                examples[category].append({
                    "split": row["_split"],
                    "axis": row["axis"],
                    "pair_id": row.get("pair_id", ""),
                    "match": claim["match"],
                    "context": claim["context"],
                })
    report = {
        "status": "IDENTITY_CLAIM_PATTERN_REPORT_DIAGNOSTIC",
        "source_files": {
            "positive": {"path": str(POSITIVE), "sha256": sha256(POSITIVE), "rows": 96},
            "negative": {"path": str(NEGATIVE), "sha256": sha256(NEGATIVE), "rows": 48},
        },
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "row_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "claim_counts": dict(sorted(by_category.items())),
        "claim_counts_by_split": dict(sorted(by_split.items())),
        "claim_counts_by_axis": dict(sorted(by_axis.items())),
        "examples": {key: value for key, value in sorted(examples.items())},
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "rows": len(rows), "output": str(OUTPUT), "claim_counts": dict(by_category)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
