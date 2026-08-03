#!/usr/bin/env python3
"""Verify the full-bundle identity-claim diagnostic report."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPORT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42/IDENTITY_CLAIM_PATTERN_REPORT_V4.json"


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["row_count"] == 273
    assert report["missing_identity_ledger_rows"] == []
    assert report["claim_counts"]["model_voice_substrate"] == 88
    assert report["claim_counts"]["viv_aios_identity"] == 31
    assert report["claim_counts"]["invented_aios_compound"] == 3
    assert report["training_authorized"] is False
    assert report["run_authorized"] is False
    assert report["optimizer_eligible"] is False
    print({"ok": True, "rows": report["row_count"], "missing_ledger": 0, "claim_categories": len(report["claim_counts"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
