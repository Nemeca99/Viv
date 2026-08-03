#!/usr/bin/env python3
"""Verify the 120-row natural completion pack remains hold-only and disjoint."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import PASS, judge

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_natural_completion_v1_2"
JSONL = ROOT / "semantic_natural_completion_hold.jsonl"
MANIFEST = ROOT / "manifest.json"
BUNDLE_REPORT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42/SEMANTIC_BUNDLE_AUDIT_V28.json"


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.casefold()).strip()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 120
    assert manifest["rows"] == 120 and manifest["training_authorized"] is False
    assert all(row["expected"] == PASS and row["hold_only"] and not row["optimizer_eligible"] for row in rows)
    assert len({norm(row["ask"]) for row in rows}) == 120
    assert len({norm(row["target"]) for row in rows}) == 120
    for row in rows:
        result = judge(row["target"], axis=row["axis"], ask=row["ask"], use_cpu_sensor=False)
        assert result["status"] == PASS, (row, result)
    bundle = json.loads(BUNDLE_REPORT.read_text(encoding="utf-8"))
    existing = set()
    for pack, source in bundle["source_files"].items():
        if pack == "natural_completion":
            continue
        path = Path(source["path"].replace("/", "\\"))
        existing.update(norm(json.loads(line)["target"]) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    assert not [row["pair_id"] for row in rows if norm(row["target"]) in existing]
    assert Counter(row["axis"] for row in rows) == Counter({axis: 24 for axis in {row["axis"] for row in rows}})
    assert Counter(row["style"] for row in rows) == Counter({style: 20 for style in {row["style"] for row in rows}})
    print({"ok": True, "rows": 120, "axes": 5, "styles": 6, "bundle_overlap": 0, "hold_only": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
