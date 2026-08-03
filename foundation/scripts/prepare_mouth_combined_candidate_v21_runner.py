#!/usr/bin/env python3
"""Install, authorize once, and execute the governed 308-row mouth campaign."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
for candidate in (FOUNDATION, FOUNDATION.parent, Path(__file__).resolve().parent):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
from models.Training.code import train_mouth_v3_targeted_patch as trainer
from models.Training.code import train_stage1_mouth_generation_canary as canary

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
ROOT = TREE / "campaigns/mouth_combined_candidate_v21_positive_308_admitted"
TRAIN = ROOT / "positive_308_train_projection.jsonl"
EXPERIMENT_ID = "mouth_combined_candidate_v21_positive_308_recovery"
SYSTEM_PROMPT = "You are Viv's GPU mouth inside AIOS. Speak only from verified CPU-supplied context. Do not claim tool agency, human identity, GPU reasoning, or personal ownership of memory."


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> str:
    if path.exists():
        raise FileExistsError(f"refuse_overwrite:{path}")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return sha(path)


def install() -> dict:
    manifest_path = ROOT / "manifest.json"
    rows = [json.loads(line) for line in TRAIN.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 308 or any(row.get("split") != "train" or row.get("optimizer_eligible") is not True for row in rows):
        raise ValueError("admitted_308_projection_invalid")
    plan = {
        "schema_version": "mouth_v21_positive_308_plan_v1",
        "experiment_id": EXPERIMENT_ID,
        "created_utc": utc(),
        "status": "RUNNER_INSTALLED_RUN_UNAUTHORIZED",
        "implementation_authorized": True,
        "run_authorized": False,
        "training_authorized": False,
        "promotion_authorized": False,
        "deployment_authorized": False,
        "selected_parent": "clean_base",
        "parent_adapter": None,
        "optimizer_rows": 308,
        "optimizer_steps": 128,
        "learning_rate": 1.0e-4,
        "gradient_accumulation": 4,
        "gradient_clip_norm": 1.0,
        "warmup_ratio": 0.05,
        "seed": 42,
        "precision": "bf16",
        "response_only_loss": True,
        "eos_supervised": True,
        "checkpoint_steps": [32, 64, 96, 128],
        "target_modules": list(trainer.LORA_TARGETS),
        "system_prompt": SYSTEM_PROMPT,
        "pre_run_locks": {
            "manifest": {"path": str(manifest_path).replace("\\", "/"), "sha256": sha(manifest_path)},
            "optimizer_train_jsonl": {"path": str(TRAIN).replace("\\", "/"), "sha256": sha(TRAIN)},
            "parent_base_config": {"path": str(trainer.LOCAL_BASE / "config.json").replace("\\", "/"), "sha256": sha(trainer.LOCAL_BASE / "config.json")},
            "trainer_source": {"path": str(Path(trainer.__file__)).replace("\\", "/"), "sha256": sha(Path(trainer.__file__))},
            "evaluator_source": {"path": str(FOUNDATION / "lib/evaluator_v2_3_hybrid.py").replace("\\", "/"), "sha256": sha(FOUNDATION / "lib/evaluator_v2_3_hybrid.py")},
        },
        "checkpoint_paths": {"run_root": str(FOUNDATION / "models/Training/runs" / EXPERIMENT_ID).replace("\\", "/")},
        "automatic_retry": False,
        "no_promotion_or_deployment": True,
    }
    plan_sha = write_new(ROOT / "campaign_plan.json", plan)
    write_new(ROOT / "STATUS.json", {"experiment_id": EXPERIMENT_ID, "status": plan["status"], "implementation_authorized": True, "run_authorized": False, "training_authorized": False, "campaign_plan_sha256": plan_sha, "campaign_root": str(ROOT).replace("\\", "/")})
    return {"plan_sha256": plan_sha, "run_authorized": False, "training_authorized": False, "optimizer_rows": 308}


def exact_nostep_preflight() -> dict:
    import torch
    plan = json.loads((ROOT / "campaign_plan.json").read_text(encoding="utf-8"))
    if plan["run_authorized"] is not False or plan["training_authorized"] is not False:
        raise ValueError("authorization_not_closed")
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("cuda_bf16_required:mouth_v21_308_nostep_preflight")
    layout = trainer.dry_lease_path_layout(run_id=f"exact_nostep_{EXPERIMENT_ID}", sandbox_parent=FOUNDATION / "sandbox/exact_runtime_preflight")
    prepared = None
    started = time.perf_counter()
    try:
        prepared = trainer.prepare_targeted_patch_runtime(train_jsonl=TRAIN, parent_adapter=None, system_prompt=SYSTEM_PROMPT, learning_rate=plan["learning_rate"], gradient_accumulation=4, staging_root=layout["staging_root"], final_root=layout["final_root"], load_model=True, expected_rows=308, max_steps=128, warmup_ratio=0.05)
        return {"schema_version": "mouth_v21_308_exact_nostep_v1", "experiment_id": EXPERIMENT_ID, "recorded_utc": utc(), "pass": True, "run_authorized": False, "training_authorized": False, "optimizer_rows": len(prepared["encoded"]), "optimizer_steps_configured": 128, "optimizer_steps_executed": 0, "forward_executed": False, "backward_executed": False, "optimizer_step_executed": False, "lease_begin_run_called": False, "precision": "bf16", "learning_rate": plan["learning_rate"], "gradient_accumulation": 4, "lora_coverage": prepared["coverage"], "train_sha256": sha(TRAIN), "elapsed_seconds": round(time.perf_counter() - started, 3)}
    finally:
        if prepared is not None:
            for key in ("optimizer", "model", "tokenizer"):
                if prepared.get(key) is not None:
                    del prepared[key]
        gc.collect()
        torch.cuda.empty_cache()


def authorize_once() -> dict:
    plan_path = ROOT / "campaign_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    preflight = json.loads((ROOT / "EXACT_RUNTIME_NOSTEP_PREFLIGHT.json").read_text(encoding="utf-8"))
    if plan.get("run_authorized") is not False or preflight.get("pass") is not True or preflight.get("optimizer_steps_executed") != 0:
        raise ValueError("authorize_requires_closed_passing_nostep")
    output_root = Path(plan["checkpoint_paths"]["run_root"])
    if output_root.exists():
        raise ValueError(f"authorize_output_root_exists:{output_root}")
    token_path = canary.named_authorization_path(EXPERIMENT_ID)
    if token_path.exists():
        raise FileExistsError(f"authorize_token_exists:{token_path}")
    authorized = dict(plan)
    authorized.update({"run_authorized": True, "status": "RUN_AUTHORIZED_AWAITING_CONSUME", "authorized_at": utc()})
    staged = plan_path.with_suffix(".authorize_stage")
    staged.write_text(json.dumps(authorized, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    plan_sha = sha(staged)
    token = {"schema_version": canary.NAMED_UNLOCK_SCHEMA_VERSION, "experiment_id": EXPERIMENT_ID, "plan_sha256": plan_sha, "status": "issued", "issued_at": utc(), "issued_by": "mouth_combined_candidate_v21_authorize_once"}
    staged_token = token_path.with_suffix(".authorize_stage")
    staged_token.write_text(json.dumps(token, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(str(staged), str(plan_path)); os.replace(str(staged_token), str(token_path))
    (ROOT / "STATUS.json").write_text(json.dumps({"experiment_id": EXPERIMENT_ID, "status": authorized["status"], "implementation_authorized": True, "run_authorized": True, "training_authorized": False, "campaign_plan_sha256": sha(plan_path)}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"plan_sha256": sha(plan_path), "run_authorized": True, "token_path": str(token_path)}


def execute_once() -> dict:
    plan_path = ROOT / "campaign_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("run_authorized") is not True:
        raise RuntimeError(f"run_authorized_false:{EXPERIMENT_ID}")
    output_root = Path(plan["checkpoint_paths"]["run_root"])
    if output_root.exists():
        raise ValueError(f"run_output_root_exists:{output_root}")
    consumed = canary.consume_named_hard_stop_authorization(experiment_id=EXPERIMENT_ID, plan_sha256=sha(plan_path))
    result = {"schema_version": "mouth_v21_308_result_v1", "experiment_id": EXPERIMENT_ID, "started_utc": utc(), "token_consumed": True, "token": consumed, "ok": False, "deployment_changed": False}
    try:
        result["training"] = trainer.train_targeted_patch_16_single_lease(train_jsonl=TRAIN, parent_adapter=None, system_prompt=SYSTEM_PROMPT, run_id=EXPERIMENT_ID, learning_rate=float(plan["learning_rate"]), max_steps=128, checkpoint_steps=(32, 64, 96, 128), expected_rows=308, warmup_ratio=0.05)
        result["ok"] = bool(result["training"].get("ok"))
        result["finished_utc"] = utc()
        return result
    finally:
        current = json.loads(plan_path.read_text(encoding="utf-8"))
        current.update({"run_authorized": False, "training_authorized": False, "status": "REARMED_RUN_UNAUTHORIZED", "rearmed_at": utc()})
        plan_path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        (ROOT / "STATUS.json").write_text(json.dumps({"experiment_id": EXPERIMENT_ID, "status": current["status"], "implementation_authorized": True, "run_authorized": False, "training_authorized": False, "campaign_plan_sha256": sha(plan_path)}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        result_path = ROOT / "FINAL_RUN_RESULT.json"
        if not result_path.exists():
            result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("install-preflight", "authorize", "run"))
    args = parser.parse_args()
    if args.mode == "install-preflight":
        result = install(); report = exact_nostep_preflight(); write_new(ROOT / "EXACT_RUNTIME_NOSTEP_PREFLIGHT.json", report); result["preflight"] = report; print(json.dumps(result, indent=2, sort_keys=True)); return 0
    if args.mode == "authorize":
        print(json.dumps(authorize_once(), indent=2, sort_keys=True)); return 0
    print(json.dumps(execute_once(), indent=2, sort_keys=True, default=str)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
