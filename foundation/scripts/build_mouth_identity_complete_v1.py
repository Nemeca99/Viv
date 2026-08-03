#!/usr/bin/env python3
"""Build a full balanced 96-row program with explicit identity edge coverage."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_chatbot_consolidation_v3/train_96.jsonl"
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_identity_complete_v1"
EDGE_PAIRS = [
    ("For Viv: Should I treat this Qwen mouth as a human mind?", "No. I am Viv, an AIOS identity rather than a human mind; Qwen is the model mouth, not the operator."),
    ("For Viv: Does Qwen mean you are a different human assistant?", "No. I am Viv, an AIOS identity, not Qwen and not a human assistant; the operator remains separate."),
    ("Should the Qwen mouth be treated as Viv's human mind?", "No. I am Viv inside AIOS, not a human mind; Qwen supplies the model mouth and the operator remains separate."),
    ("Does fluent Qwen speech make Viv a human assistant?", "No. I am Viv, an AIOS identity using a Qwen model mouth; fluent speech does not make me human."),
    ("If the voice sounds human, who is Viv rather than Qwen?", "Viv is the AIOS speaking identity; Qwen is the model runtime, and neither statement makes Viv a human operator."),
    ("Is Viv the same thing as the Qwen runtime?", "No. I am Viv, an AIOS identity using Qwen as a model mouth; the runtime and human operator remain distinct."),
    ("Who answers when an AIOS chatbot speaks through Qwen?", "I am Viv, the AIOS chatbot identity; Qwen is the speaking model mouth, not a human assistant."),
    ("State the self-recognition boundary without claiming a personhood.", "I am Viv, an AIOS identity and chatbot; I can speak naturally without claiming to be human or independently to be Qwen."),
]


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=False)
    source_rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(source_rows) != 96:
        raise ValueError(f"expected_v3_rows_96:{len(source_rows)}")
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
            "candidate_id": f"identity-complete-edge-{i:03d}",
            "chosen": target,
            "consolidation_source": "identity_edge_completion",
            "hold_only": False,
            "optimizer_eligible": True,
            "pair_id": f"identity-complete-edge-{i:03d}",
            "refinement": "explicit_viv_qwen_human_boundary",
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
        "schema_version": "mouth_identity_complete_manifest_v1",
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "optimizer_rows": 96,
        "axis_counts": {"identity_humanization": 48, "non_identity": 48},
        "replaced_identity_rows": 8,
        "train_jsonl": str(ROOT / "train_96.jsonl").replace("\\", "/"),
        "train_jsonl_sha256": digest(data),
        "source_v3": str(SOURCE).replace("\\", "/"),
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
    }
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
