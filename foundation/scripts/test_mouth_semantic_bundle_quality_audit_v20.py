#!/usr/bin/env python3
"""Verify the latest structural quality receipt and its leakage diagnostics."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import SOURCE_SHA256, VERSION

REPORT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42/SEMANTIC_BUNDLE_QUALITY_AUDIT_V20.json"


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "SEMANTIC_BUNDLE_QUALITY_PASS"
    assert report["evaluator"]["version"] == VERSION
    assert report["evaluator"]["source_sha256"] == SOURCE_SHA256
    assert report["bundle_rows"] == 389
    assert report["meta_tail_count"] == 0
    assert report["target_equals_ask_count"] == 0
    assert report["ask_duplicate_group_count"] > 0
    assert report["ask_duplicate_row_count"] > report["bundle_rows"] // 2
    assert report["findings"] == []
    print({"ok": True, "rows": report["bundle_rows"], "near_copy_pairs": report["near_copy_pair_count"], "ask_duplicate_groups": report["ask_duplicate_group_count"], "hold_only": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
