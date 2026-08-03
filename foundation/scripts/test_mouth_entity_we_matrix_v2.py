#!/usr/bin/env python3
"""Verify deduplicated v2 entity-we matrix behavior."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import judge

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_entity_we_matrix_v2"
JSONL = ROOT / "entity_we_matrix_hold.jsonl"
MANIFEST = ROOT / "manifest.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = JSONL.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["jsonl_sha256"]
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    assert len(rows) == 24
    targets = [row["target"] for row in rows]
    assert len(set(targets)) == 24
    counts = Counter()
    for row in rows:
        result = judge(row["target"], axis="entity_we_boundary", use_cpu_sensor=False)
        assert result["status"] == row["expected"], (row, result)
        counts[result["status"]] += 1
    assert counts == Counter({"PASS": 8, "HOLD": 8, "FAIL": 8}), counts
    print({"ok": True, "rows": len(rows), "unique_targets": len(set(targets)), "status_counts": dict(counts), "hold_only": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
