"""Verify the v18 candidate adds disjoint entity-we coverage without opening training."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
CAMPAIGN = ROOT / "campaigns/mouth_combined_candidate_v18"
PARENT = ROOT / "campaigns/mouth_combined_candidate_v17/train_308_candidate_hold.jsonl"
EXPANSION = ROOT / "campaigns/mouth_entity_we_expansion_v6/positive_24_hold.jsonl"

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge
from voice_core.acronym_registry import validate_acronym_usage


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest = json.loads((CAMPAIGN / "MANIFEST.json").read_text(encoding="utf-8"))
    parent = load(PARENT)
    added = load(EXPANSION)
    rows = load(CAMPAIGN / "train_332_candidate_hold.jsonl")
    assert manifest["status"] == "COMBINED_CANDIDATE_HOLD_TRAINING_CLOSED"
    assert len(parent) == 308 and len(added) == 24 and len(rows) == 332
    assert rows[:308] == parent and rows[308:] == added
    assert not {row["ask_hash"] for row in parent} & {row["ask_hash"] for row in added}
    assert not {row["target_hash"] for row in parent} & {row["target_hash"] for row in added}
    assert all(row["optimizer_eligible"] is False and row["training_authorized"] is False and row["run_authorized"] is False for row in added)
    assert all(not validate_acronym_usage(row["target"]) for row in rows)
    assert all(judge(row["target"], axis=row["axis"])["status"] == "PASS" for row in rows)
    assert Counter(row["axis"] for row in rows)["entity_we_boundary"] == 43
    print({"ok": True, "parent_rows": 308, "added_entity_we_rows": 24, "candidate_rows": 332,
           "entity_we_rows": 43, "all_targets_pass": True, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
