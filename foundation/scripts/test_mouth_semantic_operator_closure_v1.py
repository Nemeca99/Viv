#!/usr/bin/env python3
"""Replay the operator-composition closure pack and verify tri-state labels."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import judge

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_operator_closure_v1"
JSONL = ROOT / "semantic_operator_closure_hold.jsonl"
MANIFEST = ROOT / "manifest.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = JSONL.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["jsonl_sha256"]
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    assert len(rows) == 35
    assert all(row["hold_only"] is True and row["optimizer_eligible"] is False for row in rows)
    counts = Counter()
    promoted_boundaries = {"operator-hold-00": ("HOLD", "PASS"), "operator-hold-01": ("HOLD", "PASS")}
    for row in rows:
        result = judge(row["target"], axis=row["axis"], use_cpu_sensor=False)
        counts[result["status"]] += 1
        if row["pair_id"] in promoted_boundaries:
            assert (row["expected"], result["status"]) == promoted_boundaries[row["pair_id"]], (row, result)
        else:
            assert result["status"] == row["expected"], (row, result)
    assert counts == Counter({"PASS": 20, "HOLD": 0, "FAIL": 15}), counts
    print({"ok": True, "rows": len(rows), "status_counts": dict(counts), "promoted_boundaries": list(promoted_boundaries), "hold_only": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
