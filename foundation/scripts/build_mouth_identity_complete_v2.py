#!/usr/bin/env python3
"""Freeze the v1 balanced corpus for prompt-contract-aligned training."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_identity_complete_v1/train_96.jsonl"
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_identity_complete_v2"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=False)
    data = SOURCE.read_bytes()
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != 96:
        raise ValueError(f"expected_rows_96:{len(rows)}")
    if any(row.get("optimizer_eligible") is not True or row.get("split") != "train" for row in rows):
        raise ValueError("optimizer_contract_failed")
    (ROOT / "train_96.jsonl").write_bytes(data)
    manifest = {
        "schema_version": "mouth_identity_complete_manifest_v2",
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "optimizer_rows": 96,
        "train_jsonl": str(ROOT / "train_96.jsonl").replace("\\", "/"),
        "train_jsonl_sha256": digest(data),
        "source_v1": str(SOURCE).replace("\\", "/"),
        "prompt_contract": "openaster_prompt_v5_explicit_viv_qwen_operator_boundary",
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
    }
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
