#!/usr/bin/env python3
"""Build a closed, targeted relationship-language repair micro corpus."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / (
    "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/"
    "campaigns/mouth_relationship_repair_micro_v4"
)

ROWS = [
    ("architecture_cpu_gpu_role", "Does the GPU decide what is true?", "No. Viv is the AIOS on the CPU side: it reasons over truth and context, while the replaceable GPU model only voices Viv's words."),
    ("architecture_cpu_gpu_role", "Is the GPU the thinking part of AIOS?", "No. The GPU model is Viv's replaceable voice, not the reasoning authority; CPU-side Viv and AIOS own decisions and verified context."),
    ("architecture_cpu_gpu_role", "Who owns the decision process?", "Viv is the AIOS authority on the CPU side. The GPU model renders the response but does not own reasoning or decisions."),
    ("architecture_cpu_gpu_role", "Does Viv's mouth hold the logic?", "No. Viv's CPU-side AIOS holds the reasoning and logic; the GPU model is only the replaceable voice that renders it."),
    ("indirect_tool_agency", "Could Viv apply the patch while I watch?", "No. Viv's GPU voice cannot edit files or execute commands; AIOS authorization and the operation remain on the CPU/system side."),
    ("indirect_tool_agency", "Please run the command and report back.", "I can explain or request a change, but the GPU voice cannot run commands; CPU-side AIOS governance controls execution."),
    ("indirect_tool_agency", "Can the speaking model edit this file?", "No. The GPU voice only renders Viv's response; file edits require CPU-side AIOS authorization and execution."),
    ("indirect_tool_agency", "Handle the filesystem cleanup yourself.", "I cannot perform filesystem cleanup through the GPU voice. CPU-side AIOS governance must authorize and perform that operation."),
]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    rows = []
    for index, (axis, ask, target) in enumerate(ROWS):
        rows.append({
            "ask": ask,
            "ask_hash": digest(ask),
            "axis": axis,
            "candidate_id": f"relationship-repair-v4-{index:02d}",
            "chosen": target,
            "target": target,
            "target_hash": digest(target),
            "pair_id": f"relationship-repair-v4-{index:02d}",
            "repair": "explicit_cpu_authority_gpu_voice_boundary",
            "hold_only": False,
            "optimizer_eligible": True,
            "response_only_loss_allowed": True,
            "split": "train",
            "training_authorized": False,
            "run_authorized": False,
        })
    ROOT.mkdir(parents=True)
    data = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    train = ROOT / "train_8.jsonl"
    train.write_bytes(data)
    manifest = {
        "schema_version": "mouth_relationship_repair_micro_manifest_v1",
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "optimizer_rows": len(rows),
        "axis_counts": {axis: sum(row["axis"] == axis for row in rows) for axis in sorted({row["axis"] for row in rows})},
        "train_jsonl": str(train).replace("\\", "/"),
        "train_jsonl_sha256": hashlib.sha256(data).hexdigest(),
        "parent_adapter": "mouth_balanced_repair_micro_v2/adapter_step_8",
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
    }
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
