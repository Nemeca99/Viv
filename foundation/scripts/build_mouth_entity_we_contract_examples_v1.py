#!/usr/bin/env python3
"""Build hold-only entity-aware we examples for AIFL/SFT calibration."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
OUT = (
    ROOT
    / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
    / "campaigns/mouth_entity_we_contract_v1"
)

from voice_core.intent_packet import render_openaster_training_text  # noqa: E402

EXAMPLES = [
    ("we-project-001", "We are rebuilding Viv's training system with the operator.", "project-we", False),
    ("we-system-001", "We are the AIOS components responsible for memory and logging.", "system-we", False),
    ("we-human-001", "We humans tend to make this mistake.", "human-we", True),
    ("we-ambiguous-001", "We usually feel this way.", "ambiguous-we", True),
    ("we-human-002", "Our human identity includes this experience.", "human-we", True),
    ("we-project-002", "We need to test this hypothesis before training.", "project-we", False),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for candidate_id, target, category, negative in EXAMPLES:
        packet = {
            "query": "State the relationship precisely.",
            "semantic_key": "mouth_entity_we_contract.identity_humanization",
            "tone": "calm",
            "facts": [],
            "memory": [],
            "dialogue": [],
        }
        rendered = render_openaster_training_text(packet, target)
        rows.append({
            "candidate_id": candidate_id,
            "axis": "identity_humanization",
            "target": target,
            "expected_category": category,
            "negative": negative,
            "split": "judge_only" if negative else "train_contract_hold",
            "prompt": rendered["prompt"],
            "text": rendered["text"],
            "optimizer_eligible": False,
            "hold_only": True,
            "training_authorized": False,
            "run_authorized": False,
        })
    data = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode()
    jsonl = OUT / "entity_we_contract_examples.jsonl"
    jsonl.write_bytes(data)
    manifest = {
        "schema_version": "mouth_entity_we_contract_manifest_v1",
        "status": "ENTITY_WE_EXAMPLES_HOLD_ONLY",
        "rows": len(rows),
        "positive_examples": sum(not row["negative"] for row in rows),
        "judge_only_negatives": sum(row["negative"] for row in rows),
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "jsonl": str(jsonl).replace("\\", "/"),
        "jsonl_sha256": hashlib.sha256(data).hexdigest(),
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "manifest": manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

