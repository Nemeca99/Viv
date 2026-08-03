"""Verify the schema-complete v7 entity-we candidate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
EXP = ROOT / "campaigns/mouth_entity_we_candidate_v7"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest = json.loads((EXP / "MANIFEST.json").read_text(encoding="utf-8"))
    candidate = load(EXP / "train_272_candidate_hold.jsonl")
    parent = load(ROOT / "campaigns/mouth_full_run_entity_we_v2/train_256.jsonl")
    template = next(row for row in parent if row.get("axis") == "entity_we_boundary")
    assert manifest["status"] == "CANDIDATE_SCHEMA_COMPLETE_TRAINING_CLOSED"
    assert len(candidate) == 272 and candidate[:256] == parent
    assert all(set(row) == set(template) for row in candidate[256:])
    assert all(row["hold_only"] and not row["optimizer_eligible"] and not row["full_campaign_eligible"] for row in candidate[256:])
    assert manifest["parent_sha256"] == sha(ROOT / "campaigns/mouth_full_run_entity_we_v2/train_256.jsonl")
    assert manifest["candidate_sha256"] == sha(EXP / "train_272_candidate_hold.jsonl")
    assert manifest["errors"] == []
    assert manifest["admission_allowed"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    print({"ok": True, "rows": 272, "added": 16, "schema_complete": True, "parent_preserved": True, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
