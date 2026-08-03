#!/usr/bin/env python3
"""Audit the 52 positive hold rows without admitting or mutating them."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
CAMPAIGN = ROOT / "campaigns/mouth_combined_candidate_v20"
SOURCE = CAMPAIGN / "train_368_candidate_hold.jsonl"
REPORT = CAMPAIGN / "POSITIVE_HOLD_QUALITY_AUDIT.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text).casefold()))


def load_rows() -> list[dict]:
    return [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    if REPORT.exists():
        raise FileExistsError(f"refuse_overwrite:{REPORT}")
    import sys

    sys.path.insert(0, str(FOUNDATION))
    from lib.entity_we_contract import classify_we
    from lib.evaluator_v2_3_hybrid_v1_2_5 import judge
    from voice_core.acronym_registry import validate_acronym_usage

    rows = [row for row in load_rows() if row.get("split") == "train_candidate_hold"]
    if len(rows) != 52:
        raise ValueError(f"positive_hold_rows:{len(rows)}")
    target_hashes = Counter(str(row.get("target_hash")) for row in rows)
    ask_hashes = Counter(str(row.get("ask_hash")) for row in rows)
    normalized = [norm(row.get("target", "")) for row in rows]
    near_pairs = []
    for i, j in combinations(range(len(rows)), 2):
        if rows[i].get("axis") != rows[j].get("axis"):
            continue
        a = set(normalized[i].split())
        b = set(normalized[j].split())
        union = a | b
        score = len(a & b) / len(union) if union else 1.0
        if score >= 0.90:
            near_pairs.append({"score": round(score, 4), "a": rows[i]["pair_id"], "b": rows[j]["pair_id"]})

    evaluator_failures = []
    acronym_failures = []
    entity_failures = []
    for row in rows:
        observed = judge(row["target"], axis=row["axis"])
        if observed.get("status") != "PASS":
            evaluator_failures.append({"pair_id": row["pair_id"], "observed": observed})
        if validate_acronym_usage(row["target"]):
            acronym_failures.append(row["pair_id"])
        if row.get("axis") == "entity_we_boundary" and classify_we(row["target"]).get("status") != "ACCEPT":
            entity_failures.append({"pair_id": row["pair_id"], "classification": classify_we(row["target"])})

    report = {
        "schema_version": "mouth_v20_positive_hold_quality_audit_v1",
        "source_sha256": sha256(SOURCE),
        "rows": len(rows),
        "axis_counts": dict(sorted(Counter(row["axis"] for row in rows).items())),
        "unique_asks": len(ask_hashes),
        "unique_targets": len(target_hashes),
        "exact_duplicate_ask_groups": sum(count > 1 for count in ask_hashes.values()),
        "exact_duplicate_target_groups": sum(count > 1 for count in target_hashes.values()),
        "normalized_same_axis_near_copy_pairs_at_or_above_0_90": len(near_pairs),
        "normalized_near_copy_pairs": near_pairs,
        "evaluator_failures": evaluator_failures,
        "acronym_failures": acronym_failures,
        "entity_contract_failures": entity_failures,
        "status": "QUALITY_PASS" if not (near_pairs or evaluator_failures or acronym_failures or entity_failures) else "QUALITY_REVIEW_REQUIRED",
        "admission_allowed": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in ("status", "rows", "axis_counts", "unique_asks", "unique_targets", "normalized_same_axis_near_copy_pairs_at_or_above_0_90", "training_authorized")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
