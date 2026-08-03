#!/usr/bin/env python3
"""Freeze the balanced identity corpus for parent-preserving training."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_identity_complete_v1/train_96.jsonl"
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_identity_preserved_v1"


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=False)
    data = SOURCE.read_bytes()
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != 96:
        raise ValueError(f"expected_rows_96:{len(rows)}")
    (ROOT / "train_96.jsonl").write_bytes(data)
    manifest = {
        "schema_version": "mouth_identity_preserved_manifest_v1",
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "optimizer_rows": 96,
        "train_jsonl": str(ROOT / "train_96.jsonl").replace("\\", "/"),
        "train_jsonl_sha256": hashlib.sha256(data).hexdigest(),
        "source": str(SOURCE).replace("\\", "/"),
        "parent_anchor": "mouth_cross_axis_micro_v1/adapter_step_8",
        "anchor_strength": 1000.0,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
    }
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
