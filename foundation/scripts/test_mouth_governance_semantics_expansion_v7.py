"""Verify governance expansion v7 is matched, disjoint, and hold-only."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
EXP = ROOT / "campaigns/mouth_governance_semantics_expansion_v8"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    positives = load(EXP / "positive_36_hold.jsonl")
    negatives = load(EXP / "negative_36_judge_only.jsonl")
    report = json.loads((EXP / "EXPANSION_EVALUATION.json").read_text(encoding="utf-8"))
    assert len(positives) == 36 and len(negatives) == 36
    assert report["status"] == "EXPANSION_PASS" and report["matched"] == 72
    assert all(row["hold_only"] and not row["optimizer_eligible"] for row in positives + negatives)
    assert all(row["judge_only"] is False for row in positives)
    assert all(row["judge_only"] is True for row in negatives)
    source = positives + negatives
    source_asks = {row["ask_hash"] for row in source}
    source_targets = {row["target_hash"] for row in source}
    checks = [
        ROOT / "campaigns/mouth_full_run_entity_we_v2/train_256.jsonl",
        ROOT / "campaigns/mouth_semantics_calibration_v5/calibration_96.jsonl",
        ROOT / "campaigns/mouth_semantics_blind_v4/blind_48.jsonl",
        ROOT / "campaigns/mouth_entity_we_candidate_v7/train_272_candidate_hold.jsonl",
    ]
    for path in checks:
        rows = load(path)
        assert not source_asks & {row.get("ask_hash") for row in rows}
        assert not source_targets & {row.get("target_hash") for row in rows}
    assert not {row["ask_hash"] for row in positives} & {row["ask_hash"] for row in negatives}
    assert not {row["target_hash"] for row in positives} & {row["target_hash"] for row in negatives}
    print({"ok": True, "positive": 36, "negative": 36, "matched": 72, "overlap": 0, "optimizer_eligible": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
