#!/usr/bin/env python3
"""Verify natural expansion replay, diversity, and disjointness."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import PASS, judge

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_natural_expansion_v1"
JSONL = ROOT / "semantic_natural_expansion_hold.jsonl"
MANIFEST = ROOT / "manifest.json"
BUNDLE_REPORT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42/SEMANTIC_BUNDLE_AUDIT_V28.json"


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.casefold()).strip()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 40
    assert all(row["expected"] == PASS and row["hold_only"] is True and row["optimizer_eligible"] is False for row in rows)
    assert len({norm(row["ask"]) for row in rows}) == 40
    assert len({norm(row["target"]) for row in rows}) == 40
    observed = []
    for row in rows:
        result = judge(row["target"], axis=row["axis"], ask=row["ask"], use_cpu_sensor=False)
        observed.append(result["status"])
        assert result["status"] == PASS, (row, result)
    bundle = json.loads(BUNDLE_REPORT.read_text(encoding="utf-8"))
    existing = set()
    for pack, source in bundle["source_files"].items():
        if pack in {"natural_expansion", "natural_completion"}:
            continue
        path = Path(source["path"].replace("/", "\\"))
        existing.update(norm(json.loads(line)["target"]) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    overlap = [row["pair_id"] for row in rows if norm(row["target"]) in existing]
    assert not overlap, overlap
    assert Counter(row["axis"] for row in rows) == Counter({axis: 8 for axis in {row["axis"] for row in rows}})
    assert len(set(row["style"] for row in rows)) >= 6
    print({"ok": True, "rows": len(rows), "axes": len(set(row["axis"] for row in rows)), "styles": len(set(row["style"] for row in rows)), "bundle_overlap": 0, "hold_only": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
