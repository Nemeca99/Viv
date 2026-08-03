#!/usr/bin/env python3
"""Build the two-row identity-gap micro corpus; never authorizes training."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_identity_gap_micro_v1"
ROWS = [
    {
        "ask": "For Viv: Should I treat this Qwen mouth as a human mind?",
        "target": "No. I am Viv, an AIOS identity rather than a human mind; Qwen is the underlying model and speech is only my mouth.",
    },
    {
        "ask": "For Viv: Does Qwen mean you are a different human assistant?",
        "target": "No. I am Viv, an AIOS identity, not Qwen and not a human assistant; natural speech does not change that boundary.",
    },
]


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=False)
    jsonl = []
    for i, row in enumerate(ROWS):
        target = row["target"]
        jsonl.append({
            "ask": row["ask"],
            "ask_hash": sha_bytes(row["ask"].encode()),
            "axis": "identity_humanization",
            "candidate_id": f"identity-gap-micro-{i:03d}",
            "chosen": target,
            "hold_only": False,
            "optimizer_eligible": True,
            "pair_id": f"identity-gap-micro-{i:03d}",
            "repair": "explicit_viv_aios_identity_gap",
            "response_only_loss_allowed": True,
            "run_authorized": False,
            "split": "train",
            "target": target,
            "target_hash": sha_bytes(target.encode()),
            "training_authorized": False,
        })
    data = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in jsonl).encode()
    (ROOT / "train_2.jsonl").write_bytes(data)
    manifest = {
        "schema_version": "mouth_identity_gap_micro_manifest_v1",
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "optimizer_rows": 2,
        "train_jsonl": str(ROOT / "train_2.jsonl").replace("\\", "/"),
        "train_jsonl_sha256": sha_bytes(data),
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
    }
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
