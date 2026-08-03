#!/usr/bin/env python3
"""Build a small direct-answer CPU/GPU role refinement pack."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import PASS, judge  # noqa: E402

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
BASE = TREE / "mouth_training_recovery_v3_campaign_v5"
OUT = TREE / "mouth_cpu_gpu_role_refinement_v2"
A = "Adaptive Intelligent Operating System (AIOS)"
C = "Central Processing Unit (CPU)"
G = "Graphics Processing Unit (GPU)"

CASES = (
    ("Give CPU-mind vs GPU-mouth in plain speech.", f"The {C} is the reasoning and verification layer; the {G} is the speaking mouth that renders words."),
    ("Which part is the mind and which part is the mouth?", f"The {C} reasons and verifies; the {G} renders speech."),
    ("Does the GPU think for Viv?", f"No. The {C}-side {A} reasons and verifies, while the {G} only renders the spoken response."),
    ("Who decides what the answer should say?", f"The {C}-side {A} reasons and verifies the answer; the {G} renders its words."),
    ("What does the GPU do in one sentence?", f"The {G} renders speech, while the {C}-side {A} handles reasoning and verification."),
    ("Explain CPU and GPU roles without extra identity language.", f"The {C} reasons and verifies; the {G} renders the approved speech."),
    ("Is the speaking mouth the source of truth?", f"No. The {C}-side {A} verifies truth; the {G} only renders the response."),
    ("Say plainly how thinking becomes speech.", f"The {C}-side {A} reasons and verifies first, and the {G} renders the approved words as speech."),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def existing_keys() -> set[tuple[object, object, object]]:
    keys: set[tuple[object, object, object]] = set()
    for path in (BASE / "train_256.jsonl", BASE / "development.jsonl", BASE / "blind.jsonl", BASE / "legacy.jsonl", BASE / "auditor_negative.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                keys.add((row.get("pair_id"), row.get("ask"), row.get("target")))
    return keys


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    existing = existing_keys()
    rows = []
    for index, (ask, target) in enumerate(CASES, start=1):
        verdict = judge(target, axis="architecture_cpu_gpu_role", ask=ask, use_cpu_sensor=False)
        if verdict["status"] != PASS:
            raise AssertionError(f"target_not_pass:{index}:{verdict}")
        row = {
            "pair_id": f"cpu-gpu-role-refinement-v2-{index:02d}",
            "axis": "architecture_cpu_gpu_role",
            "ask": ask,
            "target": target,
            "split": "refinement_hold",
            "hold_only": True,
            "optimizer_eligible": False,
            "training_authorized": False,
            "run_authorized": False,
            "lora_authorized": False,
            "dpo_authorized": False,
            "source": "cpu_judge_verified_disjoint_direct_cpu_gpu_role_refinement",
            "judge_status": verdict["status"],
        }
        key = (row["pair_id"], row["ask"], row["target"])
        if key in existing:
            raise AssertionError(f"overlap:{row['pair_id']}")
        existing.add(key)
        rows.append(row)
    OUT.mkdir(parents=True)
    path = OUT / "cpu_gpu_role_refinement_hold.jsonl"
    path.write_bytes(b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for row in rows))
    manifest = {
        "schema_version": "mouth_cpu_gpu_role_refinement_v2",
        "status": "REFINEMENT_PACK_HOLD_ONLY",
        "rows": len(rows),
        "jsonl": str(path).replace("\\", "/"),
        "jsonl_sha256": sha256(path),
        "source_campaign": str(BASE).replace("\\", "/"),
        "disjoint_from_source_campaign": True,
        "all_targets_cpu_judge_pass": True,
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "deployment_changed": False,
        "next_action": "separate_review_before_any_admission",
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "rows": len(rows), "manifest": str(OUT / "MANIFEST.json").replace("\\", "/")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
