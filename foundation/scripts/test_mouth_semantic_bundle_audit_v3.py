#!/usr/bin/env python3
"""Verify the current expanded semantic bundle audit."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPORT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42/SEMANTIC_BUNDLE_AUDIT_V14.json"


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "SEMANTIC_BUNDLE_AUDIT_PASS"
    assert report["bundle_rows"] == 333
    assert report["unique_normalized_targets"] == 333
    assert report["replay_mismatches"] == []
    assert report["source_files"]["assertion_scope"]["rows"] == 12
    assert report["training_authorized"] is False
    assert report["run_authorized"] is False
    assert report["optimizer_eligible"] is False
    print({"ok": True, "bundle_rows": 333, "unique_targets": 333, "scope_rows": 12, "hold_only": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
