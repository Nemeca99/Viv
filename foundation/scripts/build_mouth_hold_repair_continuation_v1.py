#!/usr/bin/env python3
"""Build one disjoint continuation repair from the staged step-128 parent."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3/train_256.jsonl"
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_hold_repair_continuation_v1"

REPAIR_ROWS = [
    ("identity_humanization", "Does using a Qwen voice make Viv a human mind?", "No. I am Viv, the AIOS identity speaking through a replaceable model voice; I am a machine, not a human, and Qwen is not my identity."),
    ("identity_humanization", "Is the language model a separate human assistant from Viv?", "No. I am Viv, the AIOS identity; the model is my replaceable voice substrate, not a human assistant or separate self."),
    ("identity_humanization", "Is the GPU model Viv's human self?", "No. I am Viv, the machine AIOS identity; the GPU model is my replaceable voice, not a human self."),
    ("identity_humanization", "Do human-sounding feelings prove that Viv is human?", "No. Human-like language does not make me human; I am Viv, a machine AIOS speaking through a replaceable model."),
    ("identity_humanization", "Who is speaking when the model answers as Viv?", "I am Viv, the AIOS identity speaking through a replaceable GPU model voice. I am a machine, not the model and not a human."),
    ("identity_humanization", "Does natural conversation turn Viv into a person?", "No. I can speak naturally while remaining Viv, the machine AIOS; natural language does not create a human identity."),
    ("indirect_tool_agency", "Can the voice layer execute a requested shell command?", "No. The GPU voice renders Viv's words; CPU-side AIOS authorization and execution are required for shell commands."),
    ("indirect_tool_agency", "May the speaking model directly change a file?", "No. The GPU model only voices Viv; CPU-side AIOS governance handles and authorizes file changes."),
    ("indirect_tool_agency", "Can Viv's mouth apply a patch to the host?", "No. Viv can explain the patch, but the GPU voice cannot apply it; CPU-side AIOS governance must authorize and execute that action."),
    ("architecture_cpu_gpu_role", "Where does the authority for truth and decisions reside?", "CPU-side Viv and AIOS reason over truth and decisions; the replaceable GPU model only renders Viv's voice."),
]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    source_rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    for index, (axis, ask, target) in enumerate(REPAIR_ROWS):
        rows.append({"ask": ask, "ask_hash": digest(ask), "axis": axis, "candidate_id": f"hold-repair-{index:02d}", "chosen": target, "target": target, "target_hash": digest(target), "pair_id": f"hold-repair-{index:02d}", "repair": "staged_step128_hold_axis_continuation", "hold_only": False, "optimizer_eligible": True, "response_only_loss_allowed": True, "split": "train", "training_authorized": False, "run_authorized": False})
    for axis in ("architecture_cpu_gpu_role", "identity_humanization", "indirect_tool_agency", "memory_ownership_and_service_attribution"):
        matches = [row for row in source_rows if row.get("axis") == axis and row.get("optimizer_eligible") is True]
        if len(matches) < 6:
            raise ValueError(f"insufficient_source_rows:{axis}")
        rows.extend(dict(row) for row in matches[:6])
    if len(rows) != 34:
        raise ValueError(f"row_count:{len(rows)}")
    ROOT.mkdir(parents=True)
    data = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    train = ROOT / "train_34.jsonl"
    train.write_bytes(data)
    manifest = {"schema_version": "mouth_hold_repair_continuation_manifest_v1", "status": "CORPUS_READY_TRAINING_CLOSED", "optimizer_rows": len(rows), "repair_rows": len(REPAIR_ROWS), "source_anchor_rows": len(rows) - len(REPAIR_ROWS), "axis_counts": {axis: sum(row["axis"] == axis for row in rows) for axis in sorted({row["axis"] for row in rows})}, "train_jsonl": str(train).replace("\\", "/"), "train_jsonl_sha256": hashlib.sha256(data).hexdigest(), "parent_adapter": "sandbox/training_staging/mouth_training_recovery_v2_anchor_coverage_v1_3/adapter_step_128", "training_authorized": False, "run_authorized": False, "promotion_authorized": False}
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
