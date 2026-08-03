"""Verify the 272-row entity-we candidate is reproducible and still closed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_entity_we_candidate_v5"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    candidate = [json.loads(line) for line in (ROOT / "train_272_candidate_hold.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    parent = Path(manifest["parent_path"])
    expansion = Path(manifest["expansion_path"])
    assert manifest["status"] == "CANDIDATE_HOLD_TRAINING_CLOSED"
    assert manifest["candidate_rows"] == 272 and len(candidate) == 272
    assert manifest["parent_rows"] == 256 and manifest["expansion_rows"] == 16
    assert manifest["errors"] == []
    assert manifest["parent_bytes_preserved"] is True
    assert manifest["parent_sha256"] == sha(parent)
    assert manifest["expansion_sha256"] == sha(expansion)
    assert manifest["candidate_sha256"] == sha(ROOT / "train_272_candidate_hold.jsonl")
    assert manifest["optimizer_eligible"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["admission_allowed"] is False
    print({"ok": True, "parent_rows": 256, "added_rows": 16, "candidate_rows": 272, "parent_preserved": True, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
