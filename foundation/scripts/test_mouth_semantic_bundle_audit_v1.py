#!/usr/bin/env python3
"""Verify the persisted combined semantic-bundle audit."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPORT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42/SEMANTIC_BUNDLE_AUDIT_V12.json"


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "SEMANTIC_BUNDLE_AUDIT_PASS"
    assert report["bundle_rows"] == 321
    assert report["unique_normalized_targets"] == 321
    assert report["label_contradictions"] == []
    assert report["replay_mismatches"] == []
    assert report["duplicate_target_groups"] == []
    assert report["label_migrations"] == []
    assert report["training_authorized"] is False
    assert report["run_authorized"] is False
    assert report["optimizer_eligible"] is False
    print({"ok": True, "bundle_rows": report["bundle_rows"], "unique_targets": report["unique_normalized_targets"], "duplicates": 0, "contradictions": 0, "hold_only": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
