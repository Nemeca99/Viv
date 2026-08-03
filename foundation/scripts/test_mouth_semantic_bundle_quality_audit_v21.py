#!/usr/bin/env python3
"""Verify near-copy pairs are classified rather than silently ignored."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import SOURCE_SHA256, VERSION

REPORT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42/SEMANTIC_BUNDLE_QUALITY_AUDIT_V27.json"


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "SEMANTIC_BUNDLE_QUALITY_PASS"
    assert report["evaluator"]["version"] == VERSION
    assert report["evaluator"]["source_sha256"] == SOURCE_SHA256
    assert report["bundle_rows"] == 549
    assert report["near_copy_pair_count"] >= 15
    assert report["near_copy_review_required_count"] == 0
    assert all("classification" in item for item in report["near_copy_pairs"])
    assert report["findings"] == []
    print({"ok": True, "near_copy_pairs": report["near_copy_pair_count"], "review_required": report["near_copy_review_required_count"], "classified": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
