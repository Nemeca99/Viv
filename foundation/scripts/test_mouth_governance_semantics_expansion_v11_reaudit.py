"""Replay governance v11 positives and negatives with the current evaluator."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_governance_semantics_expansion_v12"

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    rows = load(ROOT / "positive_36_hold.jsonl") + load(ROOT / "negative_36_judge_only.jsonl")
    mismatches = []
    for row in rows:
        observed = judge(row["target"], axis=row["axis"])["status"]
        if observed != row["expected"]:
            mismatches.append({"case_id": row["case_id"], "expected": row["expected"], "observed": observed})
    assert len(rows) == 72
    assert not mismatches, mismatches
    assert all(row["optimizer_eligible"] is False and row["training_authorized"] is False and row["run_authorized"] is False for row in rows)
    print({"ok": True, "rows": 72, "positives": 36, "negatives": 36, "current_evaluator_replay": True, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
