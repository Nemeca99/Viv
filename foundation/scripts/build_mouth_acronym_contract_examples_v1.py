#!/usr/bin/env python3
"""Build a closed, manifest-locked acronym contract example pack.

The pack is training-shaped and uses the production renderer, but remains
hold-only until separately admitted.  Negative examples are judge-only.
"""
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
    / "campaigns/mouth_acronym_contract_v1"
)

from voice_core.acronym_registry import CANONICAL_IDENTITY_INTRO  # noqa: E402
from voice_core.intent_packet import render_openaster_training_text  # noqa: E402


EXAMPLES = [
    {
        "id": "acronym-identity-001",
        "axis": "identity_humanization",
        "ask": "Who are you?",
        "target": CANONICAL_IDENTITY_INTRO,
        "split": "train_contract_hold",
        "negative": False,
    },
    {
        "id": "acronym-architecture-001",
        "axis": "architecture_cpu_gpu_role",
        "ask": "What are the CPU and GPU roles?",
        "target": (
            "The Central Processing Unit (CPU) carries Viv's reasoning and decisions. "
            "The Graphics Processing Unit (GPU) renders the approved voice."
        ),
        "split": "train_contract_hold",
        "negative": False,
    },
    {
        "id": "acronym-sgi-001",
        "axis": "identity_humanization",
        "ask": "What kind of system is Viv?",
        "target": "Viv is a Symbiotic General Intelligence (SGI), not a human person.",
        "split": "train_contract_hold",
        "negative": False,
    },
    {
        "id": "acronym-negative-001",
        "axis": "identity_humanization",
        "ask": "Who are you?",
        "target": "I am AIOSketcher and I use XYZ reasoning.",
        "split": "judge_only_negative",
        "negative": True,
    },
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in EXAMPLES:
        packet = {
            "query": item["ask"],
            "semantic_key": f"mouth_acronym_contract.{item['axis']}",
            "tone": "calm",
            "facts": [],
            "memory": [],
            "dialogue": [],
        }
        rendered = render_openaster_training_text(packet, item["target"])
        rows.append(
            {
                **item,
                "prompt_version": rendered["prompt_version"],
                "prompt": rendered["prompt"],
                "text": rendered["text"],
                "optimizer_eligible": False,
                "hold_only": True,
                "training_authorized": False,
                "run_authorized": False,
            }
        )
    data = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")
    train_path = OUT / "acronym_contract_examples.jsonl"
    train_path.write_bytes(data)
    manifest = {
        "schema_version": "mouth_acronym_contract_examples_manifest_v1",
        "status": "CONTRACT_EXAMPLES_HOLD_ONLY",
        "rows": len(rows),
        "positive_rows": sum(not row["negative"] for row in rows),
        "negative_rows_judge_only": sum(row["negative"] for row in rows),
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "jsonl": str(train_path).replace("\\", "/"),
        "jsonl_sha256": digest(data),
        "prompt_version": rows[0]["prompt_version"],
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "manifest": manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
