#!/usr/bin/env python3
"""Regression for the v9 acronym-safe identity/personality corpus."""
from __future__ import annotations

import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from voice_core.acronym_registry import validate_acronym_usage  # noqa: E402


ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v9"
EXPECTED_COUNTS = {"train": 310, "validation": 48, "frozen": 21, "adversarial": 21}


def main() -> int:
    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    vocab = json.loads((ROOT / "VOCAB.json").read_text(encoding="utf-8"))
    assert manifest["row_counts"] == EXPECTED_COUNTS
    assert manifest["row_total"] == 400
    assert manifest["rows_changed_by_repair"] > 0
    assert manifest["world_knowledge_included"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert vocab["vocab_size"] == 96

    total = 0
    for split, expected in EXPECTED_COUNTS.items():
        rows = [
            json.loads(line)
            for line in (ROOT / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == expected
        for row in rows:
            assert row["source"] == "viv_identity_personality_acronym_repair_pack_v9"
            assert row["termination_marker"] in row["text"]
            assert row["response_only_target"] is True
            assert row["telemetry_allowed"] is False
            assert validate_acronym_usage(row["response"]) == [], row
            assert "master s_n" not in row["response"].casefold()
            assert "rid=" not in row["response"].casefold()
            total += 1
    assert total == 400
    print(
        "VIV_SLM_IDENTITY_PERSONALITY_V9_PASS "
        f"rows={total} splits={EXPECTED_COUNTS} changed={manifest['rows_changed_by_repair']} "
        "acronym_contract=true world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
