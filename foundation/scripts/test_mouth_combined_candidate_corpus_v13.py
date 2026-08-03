"""Verify the deduplicated v13 candidate and current evaluator replay."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
CAMPAIGN = ROOT / "campaigns/mouth_combined_candidate_v13"
SOURCE = ROOT / "campaigns/mouth_combined_candidate_v9/train_308_candidate_hold.jsonl"

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge
from voice_core.acronym_registry import validate_acronym_usage


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest = json.loads((CAMPAIGN / "MANIFEST.json").read_text(encoding="utf-8"))
    source = load(SOURCE)
    rows = load(CAMPAIGN / "train_308_candidate_hold.jsonl")
    assert manifest["status"] == "COMBINED_CANDIDATE_HOLD_TRAINING_CLOSED"
    assert len(source) == 308 and len(rows) == 308
    assert manifest["replacements"] == 64
    assert len({row["ask_hash"] for row in rows}) == 308
    assert len({row["target_hash"] for row in rows}) == 308
    assert manifest["target_duplicates"] == 0
    assert all(not validate_acronym_usage(row["target"]) for row in rows)
    assert all(judge(row["target"], axis=row["axis"])["status"] == "PASS" for row in rows)
    assert all(row.get("optimizer_eligible") is False for row in rows[272:])
    assert all(row.get("training_authorized") is False and row.get("run_authorized") is False for row in rows[272:])
    assert all(row.get("sentence_count", 0) <= 3 and row.get("approx_token_count", 0) <= 45 for row in rows)
    print({"ok": True, "rows": 308, "unique_asks": 308, "unique_targets": 308,
           "replacements": 64, "all_targets_pass": True, "training_authorized": False,
           "axes": dict(sorted(Counter(row["axis"] for row in rows).items()))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
