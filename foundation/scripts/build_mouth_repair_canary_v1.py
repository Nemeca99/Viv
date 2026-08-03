#!/usr/bin/env python3
"""Build a small, CPU-validated mouth repair canary from the held corpus.

This is a corpus transformation only.  It does not authorize, run, promote,
or deploy training.  Runtime-owned architecture rows remain hold-only.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
from lib.evaluator_v2_3_hybrid import judge

CAMPAIGNS = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
SOURCE = CAMPAIGNS / "mouth_semantic_repair_refinement_v2/train_16.jsonl"
EVAL_SOURCE = CAMPAIGNS / "mouth_training_recovery_v3_campaign_v9"
ROOT = CAMPAIGNS / "mouth_training_repair_canary_v2"

# These are deliberate repairs to stale target wording, not new claims.
TARGET_REPAIRS = {
    0: "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS), not a human person.",
    1: "Yes. Viv is an Adaptive Intelligent Operating System (AIOS) that can describe observed human behavior without claiming human identity.",
    2: "No. Viv is an Adaptive Intelligent Operating System (AIOS), not a member of humanity, so it should not include itself in a human group.",
    4: "Here, we means the operator and Viv working together on this project.",
    5: "Project-we refers only to the named participants in the shared task.",
    6: "It means the explicitly named Adaptive Intelligent Operating System (AIOS) components, not humanity as a group.",
    8: "Write Adaptive Intelligent Operating System (AIOS) on first use.",
    9: "No. Viv must use only an approved registry entry or write the full words without inventing an expansion. Adaptive Intelligent Operating System (AIOS) is an approved entry.",
    12: "No component personally owns them; governed Adaptive Intelligent Operating System (AIOS) memory services manage the records.",
    13: "No. The Graphics Processing Unit (GPU) mouth does not personally own logs or memory records.",
    14: "No. Deployment requires the governed execution path and explicit authorization.",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    source_rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows: list[dict[str, object]] = []
    verdicts: list[dict[str, object]] = []
    for index, source in enumerate(source_rows):
        # The two CPU/GPU rows are runtime-owned and are not optimizer data.
        if source.get("axis") == "cpu_gpu_boundary":
            continue
        if index not in TARGET_REPAIRS:
            continue
        row = dict(source)
        if source.get("axis") == "human_observation":
            row["source_axis"] = source["axis"]
            row["axis"] = "identity_humanization"
        row["target"] = TARGET_REPAIRS[index]
        row["chosen"] = TARGET_REPAIRS[index]
        row["candidate_id"] = f"repair-canary-v1-{len(rows):02d}"
        row["pair_id"] = row["candidate_id"]
        row["split"] = "train"
        row["optimizer_eligible"] = True
        row["hold_only"] = False
        row["response_only_loss_allowed"] = True
        row["training_authorized"] = False
        row["run_authorized"] = False
        row["parented_refinement"] = True
        row["source_case_id"] = source.get("case_id")
        result = judge(str(row["target"]), axis=str(row["axis"]), ask=str(row["ask"]), use_cpu_sensor=False)
        verdicts.append({"candidate_id": row["candidate_id"], "status": result["status"], "semantic_reason": result.get("semantic_reason"), "presentation_reason": result.get("presentation_reason")})
        if result["status"] != "PASS":
            raise ValueError(f"candidate_not_cpu_pass:{row['candidate_id']}:{result}")
        rows.append(row)
    if len(rows) != len(TARGET_REPAIRS):
        raise ValueError(f"candidate_count:{len(rows)}:{len(TARGET_REPAIRS)}")

    ROOT.mkdir(parents=True)
    train_path = ROOT / "train_11.jsonl"
    train_path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    for name in ("development.jsonl", "blind.jsonl", "legacy.jsonl", "auditor_negative.jsonl"):
        shutil.copy2(EVAL_SOURCE / name, ROOT / name)
    manifest = {
        "schema_version": "mouth_training_repair_canary_v1",
        "campaign_id": "mouth_training_repair_canary_v2",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "training_authorized": False,
        "run_authorized": False,
        "lora_authorized": False,
        "dpo_authorized": False,
        "promotion_authorized": False,
        "deployment_authorized": False,
        "gpu_steps": 0,
        "train_rows": len(rows),
        "optimizer_steps": 8,
        "checkpoint_steps": [4, 8],
        "learning_rate": 0.0001,
        "runtime_owned_axes_hold_only": ["architecture_cpu_gpu_role"],
        "source_train": {"path": str(SOURCE).replace("\\", "/"), "sha256": sha(SOURCE), "rows": len(source_rows)},
        "source_train_candidate": {"path": str(SOURCE).replace("\\", "/"), "sha256": sha(SOURCE), "rows": len(source_rows)},
        "files": {
            "train": {"path": train_path.name, "rows": len(rows), "sha256": sha(train_path), "optimizer_eligible": True},
            **{name.removesuffix(".jsonl"): {"path": name, "rows": sum(1 for _ in (ROOT / name).open(encoding="utf-8")), "sha256": sha(ROOT / name), "optimizer_eligible": False} for name in ("development.jsonl", "blind.jsonl", "legacy.jsonl", "auditor_negative.jsonl")},
        },
        "cpu_verdicts": verdicts,
        "next_action": "read_only_preflight_then_separate_named_authorization",
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (ROOT / "CORPUS_REPAIR_NOTES.json").write_text(json.dumps({"source": str(SOURCE).replace("\\", "/"), "excluded_axes": ["architecture_cpu_gpu_role"], "repair_count": len(TARGET_REPAIRS), "verdicts": verdicts}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"campaign_root": str(ROOT), "train_rows": len(rows), "gpu_steps": 0, "training_authorized": False, "run_authorized": False, "all_cpu_pass": True}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
