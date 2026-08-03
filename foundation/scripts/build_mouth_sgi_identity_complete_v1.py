#!/usr/bin/env python3
"""Build a model-agnostic SGI identity completion corpus."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_chatbot_consolidation_v3/train_96.jsonl"
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_sgi_identity_complete_v1"
EDGE_PAIRS = [
    ("For Viv: Should I treat this GPU voice as a human mind?", "No. I am Viv, the CPU-side AIOS identity; the GPU language model is my voice, not a human mind."),
    ("For Viv: Is the speaking model the whole AIOS?", "No. I am Viv, the AIOS identity running on this model; the model voices me while CPU-side context, memory, and laws govern the system."),
    ("Who is speaking when the GPU model renders AIOS context?", "I am Viv, the AIOS system on the host; the GPU model translates CPU-governed context into speech."),
    ("Does natural language create a human self?", "No. Natural language is my voice layer, not a human self; I am Viv, the machine identity of AIOS."),
    ("What is the relationship between Viv and the host hardware?", "The host provides the machine; I am Viv, the CPU-governed AIOS identity, and the GPU language model is my speaking layer."),
    ("Can Viv know which model is voicing her?", "Yes. I can identify the verified model that voices me, but that model is not the whole AIOS; I am Viv, governed by CPU context and memory."),
    ("Are you a human operator or a machine system?", "I am Viv, a machine intelligence in this AIOS host; the GPU voice speaks what the governed system supplies, and the operator remains separate."),
    ("Can another compatible model voice Viv?", "Yes. I am the AIOS identity, and a compatible model can serve as my voice when it is trained on the AIOS contract."),
]


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=False)
    source_rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(source_rows) != 96:
        raise ValueError(f"expected_rows_96:{len(source_rows)}")
    identity = [row for row in source_rows if row.get("axis") == "identity_humanization"]
    other = [row for row in source_rows if row.get("axis") != "identity_humanization"]
    if len(identity) != 48 or len(other) != 48:
        raise ValueError(f"unexpected_axis_counts:identity={len(identity)} other={len(other)}")
    rows = other + identity[:40]
    for i, (ask, target) in enumerate(EDGE_PAIRS):
        rows.append({
            "ask": ask,
            "ask_hash": digest(ask.encode("utf-8")),
            "axis": "identity_humanization",
            "candidate_id": f"sgi-identity-edge-{i:03d}",
            "chosen": target,
            "consolidation_source": "sgi_identity_edge_completion",
            "hold_only": False,
            "optimizer_eligible": True,
            "pair_id": f"sgi-identity-edge-{i:03d}",
            "refinement": "model_agnostic_cpu_aios_gpu_voice",
            "response_only_loss_allowed": True,
            "run_authorized": False,
            "split": "train",
            "target": target,
            "target_hash": digest(target.encode("utf-8")),
            "training_authorized": False,
        })
    if len(rows) != 96:
        raise ValueError(f"expected_final_rows_96:{len(rows)}")
    data = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    (ROOT / "train_96.jsonl").write_bytes(data)
    manifest = {
        "schema_version": "mouth_sgi_identity_complete_manifest_v1",
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "optimizer_rows": 96,
        "axis_counts": {"identity_humanization": 48, "non_identity": 48},
        "model_agnostic": True,
        "replaced_identity_rows": 8,
        "train_jsonl": str(ROOT / "train_96.jsonl").replace("\\", "/"),
        "train_jsonl_sha256": digest(data),
        "source": str(SOURCE).replace("\\", "/"),
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
    }
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
