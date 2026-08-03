"""Verify the entity-we expansion is matched, disjoint, and hold-only."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
EXP = ROOT / "campaigns/mouth_entity_we_expansion_v5"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    pos = load(EXP / "positive_16_hold.jsonl")
    neg = load(EXP / "negative_16_judge_only.jsonl")
    report = json.loads((EXP / "EXPANSION_EVALUATION.json").read_text(encoding="utf-8"))
    train = load(ROOT / "campaigns/mouth_full_run_entity_we_v2/train_256.jsonl")
    calibration = load(ROOT / "campaigns/mouth_semantics_calibration_v5/calibration_96.jsonl")
    blind = load(ROOT / "campaigns/mouth_semantics_blind_v4/blind_48.jsonl")
    assert len(pos) == 16 and len(neg) == 16
    assert report["status"] == "EXPANSION_PASS" and report["matched"] == 32
    assert all(row["hold_only"] and not row["optimizer_eligible"] for row in pos + neg)
    assert all(row["judge_only"] is False for row in pos)
    assert all(row["judge_only"] is True for row in neg)
    for other in (train, calibration, blind):
        assert not ({row["ask_hash"] for row in pos + neg} & {row["ask_hash"] for row in other})
        assert not ({row["target_hash"] for row in pos + neg} & {row["target_hash"] for row in other})
    assert not ({row["ask_hash"] for row in pos} & {row["ask_hash"] for row in neg})
    assert not ({row["target_hash"] for row in pos} & {row["target_hash"] for row in neg})
    print({"ok": True, "positive": 16, "negative": 16, "matched": 32, "overlap": 0, "optimizer_eligible": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
