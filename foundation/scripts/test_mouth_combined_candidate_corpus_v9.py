"""Verify the combined 308-row candidate preserves parent metadata and closes new rows."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
CAMPAIGN = ROOT / "campaigns/mouth_combined_candidate_v9"
ENTITY = ROOT / "campaigns/mouth_entity_we_candidate_v7/train_272_candidate_hold.jsonl"
GOV = ROOT / "campaigns/mouth_governance_candidate_v8/positive_36_candidate_hold.jsonl"

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest = json.loads((CAMPAIGN / "MANIFEST.json").read_text(encoding="utf-8"))
    entity = load(ENTITY)
    governance = load(GOV)
    candidate = load(CAMPAIGN / "train_308_candidate_hold.jsonl")

    assert manifest["status"] == "COMBINED_CANDIDATE_HOLD_TRAINING_CLOSED"
    assert len(entity) == 272 and len(governance) == 36 and len(candidate) == 308
    assert candidate[:272] == entity and candidate[272:] == governance
    assert manifest["entity_source_sha256"]
    assert manifest["governance_source_sha256"]
    assert manifest["candidate_sha256"]
    assert manifest["admission_allowed"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert all(row["optimizer_eligible"] is False for row in governance)
    assert all(row["training_authorized"] is False and row["run_authorized"] is False for row in governance)
    assert len({row["ask_hash"] for row in governance}) == 36
    assert len({row["target_hash"] for row in governance}) == 36
    assert not {row["ask_hash"] for row in governance} & {row["ask_hash"] for row in entity}
    assert not {row["target_hash"] for row in governance} & {row["target_hash"] for row in entity}

    statuses = [judge(row["target"], axis=row["axis"])["status"] for row in candidate]
    assert statuses == ["PASS"] * 308
    axis_counts = Counter(row["axis"] for row in candidate)
    assert axis_counts == Counter(manifest["axis_counts"])

    # Parent metadata is intentionally preserved; only appended rows are required to be closed.
    assert any(row.get("optimizer_eligible") is True for row in entity)
    print({"ok": True, "entity_rows": 272, "governance_rows": 36, "candidate_rows": 308,
           "all_targets_pass": True, "new_rows_hold_only": True, "admission_allowed": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
