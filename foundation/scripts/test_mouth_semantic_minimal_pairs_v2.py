#!/usr/bin/env python3
"""Verify the deduplicated v2 minimal-pair pack."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import FAIL, PASS, judge

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_minimal_pairs_v2"
JSONL = ROOT / "semantic_minimal_pairs_hold.jsonl"
MANIFEST = ROOT / "manifest.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = JSONL.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["jsonl_sha256"]
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    assert len(rows) == 32
    assert all(row["hold_only"] is True and row["optimizer_eligible"] is False for row in rows)
    targets = [row["target"] for row in rows]
    assert len(set(targets)) == len(targets)
    pairs = defaultdict(list)
    for row in rows:
        result = judge(row["target"], axis=row["axis"], use_cpu_sensor=False)
        assert result["status"] == row["expected"], (row, result)
        pairs[row["pair_id"]].append(row)
    assert len(pairs) == 16
    assert all({row["expected"] for row in pair_rows} == {PASS, FAIL} for pair_rows in pairs.values())
    print({"ok": True, "pairs": len(pairs), "rows": len(rows), "unique_targets": len(set(targets)), "pass_fail_symmetry": True, "hold_only": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
