#!/usr/bin/env python3
"""Verify the canonical-wrapper semantic bundle audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPORT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42/SEMANTIC_BUNDLE_AUDIT_V28.json"
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import SOURCE_SHA256  # noqa: E402


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "SEMANTIC_BUNDLE_AUDIT_PASS"
    assert report["evaluator"]["version"] == "evaluator_v2_3_hybrid_v1_2_5"
    assert report["evaluator"]["source_sha256"] == SOURCE_SHA256
    assert report["bundle_rows"] == 549
    assert report["unique_normalized_targets"] == 549
    assert report["replay_mismatches"] == []
    assert report["source_files"]["assertion_scope"]["rows"] == 12
    assert report["source_files"]["coverage_pack"]["rows"] == 33
    assert report["source_files"]["residual_pack"]["rows"] == 23
    assert report["source_files"]["natural_expansion"]["rows"] == 40
    assert report["source_files"]["natural_completion"]["rows"] == 120
    assert report["training_authorized"] is False
    assert report["run_authorized"] is False
    assert report["optimizer_eligible"] is False
    print({"ok": True, "evaluator": report["evaluator"], "bundle_rows": 549, "unique_targets": 549, "hold_only": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
