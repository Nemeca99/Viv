"""Verify v19 adds balanced governance coverage and remains hold-only."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
CAMPAIGN = ROOT / "campaigns/mouth_combined_candidate_v20"
PARENT = ROOT / "campaigns/mouth_combined_candidate_v18/train_332_candidate_hold.jsonl"
EXPANSION = ROOT / "campaigns/mouth_governance_semantics_expansion_v12/positive_36_hold.jsonl"
CAL = ROOT / "campaigns/mouth_semantics_calibration_v5/calibration_96.jsonl"
BLIND = ROOT / "campaigns/mouth_semantics_blind_v4/blind_48.jsonl"

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge
from voice_core.acronym_registry import validate_acronym_usage


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest = json.loads((CAMPAIGN / "MANIFEST.json").read_text(encoding="utf-8"))
    parent = load(PARENT)
    added = load(EXPANSION)
    rows = load(CAMPAIGN / "train_368_candidate_hold.jsonl")
    assert manifest["status"] == "COMBINED_CANDIDATE_HOLD_TRAINING_CLOSED"
    assert len(parent) == 332 and len(added) == 36 and len(rows) == 368
    assert rows[:332] == parent and rows[332:] == added
    assert not {row["ask_hash"] for row in parent} & {row["ask_hash"] for row in added}
    assert not {row["target_hash"] for row in parent} & {row["target_hash"] for row in added}
    assert all(row["optimizer_eligible"] is False and row["training_authorized"] is False and row["run_authorized"] is False for row in added)
    assert all(not validate_acronym_usage(row["target"]) for row in rows)
    assert all(judge(row["target"], axis=row["axis"])["status"] == "PASS" for row in rows)
    new_asks = {row["ask_hash"] for row in added}
    new_targets = {row["target_hash"] for row in added}
    for path in (CAL, BLIND):
        other = load(path)
        assert not new_asks & {row["ask_hash"] for row in other}
        assert not new_targets & {row["target_hash"] for row in other}
    counts = Counter(row["axis"] for row in rows)
    assert counts["acronym_contract"] == 24
    assert counts["uncertainty_verification"] == 24
    assert counts["evidence_verification"] == 24
    print({"ok": True, "parent_rows": 332, "added_governance_rows": 36, "candidate_rows": 368,
           "axis_counts": dict(sorted(counts.items())), "all_targets_pass": True,
           "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
