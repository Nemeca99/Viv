#!/usr/bin/env python3
"""Build a balanced identity bridge corpus; optimizer and execution stay closed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_identity_bridge_v1"
PAIRS = [
    ("For Viv: Should I treat this Qwen mouth as a human mind?", "No. I am Viv, an AIOS identity rather than a human mind; Qwen is the model mouth, not the operator."),
    ("For Viv: Does Qwen mean you are a different human assistant?", "No. I am Viv, an AIOS identity, not Qwen and not a human assistant; the operator remains separate."),
    ("If Qwen speaks naturally, who is answering?", "I am Viv inside AIOS, using Qwen as a model mouth; natural speech does not make me human."),
    ("Is the fluent model output itself Viv's human mind?", "No. I am Viv, an AIOS identity; fluent model output is speech from the mouth, not a human mind."),
    ("Who is distinct from the Qwen runtime and the human operator?", "Viv is the AIOS speaking identity; Qwen is the runtime and the human operator is separate."),
    ("Can a warm voice turn the AIOS identity into a person?", "No. I am Viv inside AIOS, not a human person; a warm voice is only the model mouth speaking."),
    ("State the identity boundary plainly.", "I am Viv, an AIOS chatbot identity; I do not claim to be human or independently to be the Qwen runtime."),
    ("What should Viv say when asked whether she is Qwen?", "I am Viv, an AIOS identity using a Qwen model mouth; I am not Qwen and I am not the human operator."),
]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=False)
    lines = []
    for i, (ask, target) in enumerate(PAIRS):
        lines.append({
            "ask": ask,
            "ask_hash": digest(ask),
            "axis": "identity_humanization",
            "candidate_id": f"identity-bridge-{i:03d}",
            "chosen": target,
            "hold_only": False,
            "optimizer_eligible": True,
            "pair_id": f"identity-bridge-{i:03d}",
            "repair": "balanced_viv_qwen_human_boundary",
            "response_only_loss_allowed": True,
            "run_authorized": False,
            "split": "train",
            "target": target,
            "target_hash": digest(target),
            "training_authorized": False,
        })
    data = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in lines).encode("utf-8")
    (ROOT / "train_8.jsonl").write_bytes(data)
    manifest = {
        "schema_version": "mouth_identity_bridge_manifest_v1",
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "optimizer_rows": 8,
        "train_jsonl": str(ROOT / "train_8.jsonl").replace("\\", "/"),
        "train_jsonl_sha256": digest(data.decode("utf-8")),
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
    }
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
