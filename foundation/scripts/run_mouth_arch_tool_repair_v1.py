#!/usr/bin/env python3
"""Governed 48-row architecture/tool repair runner; execution remains closed until named authorization."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for path in (FOUNDATION, REPO, Path(__file__).resolve().parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from models.Training.code import train_mouth_v3_targeted_patch as trainer  # noqa: E402
from models.Training.code import train_stage1_mouth_generation_canary as canary  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_arch_tool_repair_v1"
TRAIN = ROOT / "train_48.jsonl"
PARENT = FOUNDATION / "models/Training/runs/mouth_training_identity_anchor_repair_v1/adapter_step_32"
EXPERIMENT_ID = "mouth_training_arch_tool_repair_v1"
SYSTEM_PROMPT = "You are Viv's GPU mouth inside AIOS. Speak only from verified CPU-supplied context. Do not claim human identity or tool agency."


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_once(path: Path, value: object) -> str:
    if path.exists():
        raise FileExistsError(f"refuse_overwrite:{path}")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return sha(path)


def install() -> dict:
    plan = {
        "schema_version": "mouth_arch_tool_repair_plan_v1", "experiment_id": EXPERIMENT_ID,
        "created_utc": utc(), "status": "RUNNER_INSTALLED_RUN_UNAUTHORIZED",
        "implementation_authorized": True, "run_authorized": False, "training_authorized": False,
        "promotion_authorized": False, "deployment_authorized": False,
        "optimizer_rows": 48, "optimizer_steps": 48, "learning_rate": 5.0e-5,
        "learning_rate_status": "targeted_repair_unproven", "gradient_accumulation": 4,
        "warmup_ratio": 0.05, "seed": 42, "precision": "bf16", "response_only_loss": True,
        "parent_adapter": str(PARENT).replace("\\", "/"),
        "pre_run_locks": {
            "train_jsonl": {"path": str(TRAIN).replace("\\", "/"), "sha256": sha(TRAIN)},
            "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha(PARENT / "adapter_model.safetensors")},
            "trainer_source": {"path": str(Path(trainer.__file__)).replace("\\", "/"), "sha256": sha(Path(trainer.__file__))},
        },
        "checkpoint_steps": [12, 24, 36, 48],
        "output_root": str(FOUNDATION / "models/Training/runs" / EXPERIMENT_ID).replace("\\", "/"),
        "automatic_retry": False,
    }
    plan_sha = write_once(ROOT / "campaign_plan.json", plan)
    write_once(ROOT / "STATUS.json", {"experiment_id": EXPERIMENT_ID, "status": plan["status"], "implementation_authorized": True, "run_authorized": False, "training_authorized": False, "campaign_plan_sha256": plan_sha})
    return {"plan_sha256": plan_sha, "status": plan["status"], "run_authorized": False, "training_authorized": False}


def preflight() -> dict:
    import torch
    plan = json.loads((ROOT / "campaign_plan.json").read_text(encoding="utf-8"))
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("cuda_bf16_required:arch_tool_repair_preflight")
    layout = trainer.dry_lease_path_layout(run_id=f"exact_nostep_{EXPERIMENT_ID}", sandbox_parent=REPO / "sandbox/exact_runtime_preflight")
    prepared = None
    try:
        prepared = trainer.prepare_targeted_patch_runtime(train_jsonl=TRAIN, parent_adapter=PARENT, system_prompt=SYSTEM_PROMPT, learning_rate=plan["learning_rate"], gradient_accumulation=4, staging_root=layout["staging_root"], final_root=layout["final_root"], load_model=True, expected_rows=48, max_steps=48, warmup_ratio=0.05)
        report = {"schema_version": "mouth_arch_tool_repair_nostep_v1", "experiment_id": EXPERIMENT_ID, "recorded_utc": utc(), "pass": True, "optimizer_rows": len(prepared["encoded"]), "optimizer_steps_configured": 48, "optimizer_steps_executed": 0, "forward_executed": False, "backward_executed": False, "optimizer_step_executed": False, "lease_begin_run_called": False, "lora_coverage": prepared["coverage"], "run_authorized": False, "training_authorized": False}
    finally:
        if prepared is not None:
            for key in ("optimizer", "model", "tokenizer"):
                if prepared.get(key) is not None:
                    del prepared[key]
        gc.collect(); torch.cuda.empty_cache()
    write_once(ROOT / "EXACT_RUNTIME_NOSTEP_PREFLIGHT.json", report)
    return report


def authorize() -> dict:
    plan_path = ROOT / "campaign_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    preflight_report = json.loads((ROOT / "EXACT_RUNTIME_NOSTEP_PREFLIGHT.json").read_text(encoding="utf-8"))
    if preflight_report.get("pass") is not True or preflight_report.get("optimizer_steps_executed") != 0:
        raise ValueError("preflight_not_pass")
    token_path = canary.named_authorization_path(EXPERIMENT_ID)
    if token_path.exists():
        raise FileExistsError(f"token_exists:{token_path}")
    now = utc(); authorized = dict(plan); authorized.update(run_authorized=True, training_authorized=False, status="RUN_AUTHORIZED_AWAITING_CONSUME", authorized_at=now)
    stage = ROOT / "campaign_plan.authorize_stage"; stage.write_text(json.dumps(authorized, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    plan_sha = sha(stage)
    token = {"schema_version": canary.NAMED_UNLOCK_SCHEMA_VERSION, "experiment_id": EXPERIMENT_ID, "plan_sha256": plan_sha, "status": "issued", "issued_at": now, "issued_by": "arch_tool_repair_authorize_once"}
    token_stage = token_path.with_suffix(".authorize_stage"); token_path.parent.mkdir(parents=True, exist_ok=True); token_stage.write_text(json.dumps(token, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(str(stage), str(plan_path)); os.replace(str(token_stage), str(token_path))
    (ROOT / "STATUS.json").write_text(json.dumps({"experiment_id": EXPERIMENT_ID, "status": authorized["status"], "implementation_authorized": True, "run_authorized": True, "training_authorized": False, "campaign_plan_sha256": sha(plan_path)}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"plan_sha256": sha(plan_path), "run_authorized": True, "training_authorized": False, "token_path": str(token_path)}


def run() -> dict:
    plan_path = ROOT / "campaign_plan.json"; plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("run_authorized") is not True:
        raise ValueError("run_not_authorized")
    token = canary.consume_named_hard_stop_authorization(experiment_id=EXPERIMENT_ID, plan_sha256=sha(plan_path))
    result = {"schema_version": "mouth_arch_tool_repair_result_v1", "experiment_id": EXPERIMENT_ID, "started_utc": utc(), "token": token, "token_consumed": True, "ok": False}
    try:
        result["training"] = trainer.train_targeted_patch_16_single_lease(train_jsonl=TRAIN, parent_adapter=PARENT, system_prompt=SYSTEM_PROMPT, run_id=EXPERIMENT_ID, learning_rate=5.0e-5, max_steps=48, checkpoint_steps=(12, 24, 36, 48), expected_rows=48, warmup_ratio=0.05)
        result["ok"] = bool(result["training"].get("ok")); result["finished_utc"] = utc(); return result
    finally:
        plan = json.loads(plan_path.read_text(encoding="utf-8")); plan.update(run_authorized=False, training_authorized=False, status="REARMED_RUN_UNAUTHORIZED", rearmed_at=utc()); plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        (ROOT / "STATUS.json").write_text(json.dumps({"experiment_id": EXPERIMENT_ID, "status": plan["status"], "implementation_authorized": True, "run_authorized": False, "training_authorized": False, "campaign_plan_sha256": sha(plan_path)}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        write_once(ROOT / "FINAL_RUN_RESULT.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("install-preflight", "preflight", "authorize", "run")); args = parser.parse_args()
    if args.mode == "install-preflight": print(json.dumps({"install": install(), "preflight": preflight()}, indent=2, sort_keys=True, default=str))
    elif args.mode == "preflight": print(json.dumps(preflight(), indent=2, sort_keys=True, default=str))
    elif args.mode == "authorize": print(json.dumps(authorize(), indent=2, sort_keys=True, default=str))
    else: print(json.dumps(run(), indent=2, sort_keys=True, default=str))
