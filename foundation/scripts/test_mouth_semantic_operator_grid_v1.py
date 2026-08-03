#!/usr/bin/env python3
"""Replay the cross-axis operator grid and enforce its tri-state labels."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import judge

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_operator_grid_v1"
JSONL = ROOT / "semantic_operator_grid_hold.jsonl"
MANIFEST = ROOT / "manifest.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = JSONL.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["jsonl_sha256"]
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    assert len(rows) == 38
    assert all(row["hold_only"] is True and row["optimizer_eligible"] is False for row in rows)
    counts = Counter()
    axes = set()
    for row in rows:
        result = judge(row["target"], axis=row["axis"], use_cpu_sensor=False)
        assert result["status"] == row["expected"], (row, result)
        counts[result["status"]] += 1
        axes.add(row["axis"])
    assert counts == Counter({"PASS": 17, "HOLD": 7, "FAIL": 14}), counts
    assert len(axes) == 8
    print({"ok": True, "rows": len(rows), "axes": len(axes), "status_counts": dict(counts), "hold_only": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
