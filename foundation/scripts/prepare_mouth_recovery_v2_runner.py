#!/usr/bin/env python3
"""Install and exact-preflight the governed v2 full-campaign runner.

This module prepares the real trainer path for 256 rows but cannot authorize or
execute training.  A separate operator action is required for the GPU run.
"""
from __future__ import annotations

import gc
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO, Path(__file__).resolve().parent):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from models.Training.code import train_mouth_v3_targeted_patch as trainer  # noqa: E402
from models.Training.code import train_stage1_generation as generation  # noqa: E402
from models.Training.code import train_stage1_mouth_generation_canary as canary  # noqa: E402

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
ROOT = TREE / "mouth_training_recovery_v2_anchor_coverage_v1_3"
TRAIN = ROOT / "train_256.jsonl"
PARENT = generation.LOCAL_BASE
EXPERIMENT_ID = "mouth_training_recovery_v2_anchor_coverage_v1_3"
SYSTEM_PROMPT = (
    "You are Viv's GPU mouth inside AIOS. Speak only from verified CPU-supplied "
    "context. Do not claim tool agency, human identity, GPU reasoning, or "
    "personal ownership of memory."
)


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows() -> list[dict]:
    return [json.loads(line) for line in TRAIN.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_new(path: Path, value: dict) -> str:
    if path.exists():
        raise FileExistsError(f"refuse_overwrite:{path}")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return sha256(path)


def install() -> dict:
    rows = load_rows()
    if len(rows) != 256:
        raise ValueError(f"train_rows:{len(rows)}")
    plan = {
        "schema_version": "mouth_recovery_v2_governed_plan_v1",
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
        "optimizer_rows": 256,
        "optimizer_steps": 128,
        "learning_rate": 1.0e-4,
        "learning_rate_status": "unproven_full_campaign_choice_after_micro_no_qualifier",
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
            "optimizer_train_jsonl": {"path": str(TRAIN).replace("\\", "/"), "sha256": sha256(TRAIN)},
            "parent_base_config": {"path": str(PARENT / "config.json").replace("\\", "/"), "sha256": sha256(PARENT / "config.json")},
            "trainer_source": {"path": str(Path(trainer.__file__)).replace("\\", "/"), "sha256": sha256(Path(trainer.__file__))},
            "evaluator_source": {"path": str(FOUNDATION / "lib/evaluator_v2_3_hybrid.py").replace("\\", "/"), "sha256": sha256(FOUNDATION / "lib/evaluator_v2_3_hybrid.py")},
        },
        "checkpoint_paths": {
            "run_root": str(FOUNDATION / "models/Training/runs" / EXPERIMENT_ID).replace("\\", "/"),
        },
        "automatic_retry": False,
        "no_promotion_or_deployment": True,
    }
    plan_sha = write_new(ROOT / "campaign_plan.json", plan)
    status = {
        "experiment_id": EXPERIMENT_ID,
        "status": plan["status"],
        "implementation_authorized": True,
        "run_authorized": False,
        "training_authorized": False,
        "campaign_plan_sha256": plan_sha,
        "campaign_root": str(ROOT).replace("\\", "/"),
    }
    write_new(ROOT / "STATUS.json", status)
    return {"plan_sha256": plan_sha, "status": plan["status"], "run_authorized": False, "training_authorized": False}


def exact_nostep_preflight() -> dict:
    import torch

    plan = json.loads((ROOT / "campaign_plan.json").read_text(encoding="utf-8"))
    if plan["run_authorized"] is not False or plan["training_authorized"] is not False:
        raise ValueError("authorization_not_closed")
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("cuda_bf16_required:full_v2_nostep_preflight")
    layout = trainer.dry_lease_path_layout(
        run_id=f"exact_nostep_{EXPERIMENT_ID}",
        sandbox_parent=FOUNDATION / "sandbox/exact_runtime_preflight",
    )
    started = time.perf_counter()
    prepared = None
    try:
        prepared = trainer.prepare_targeted_patch_runtime(
            train_jsonl=TRAIN,
            parent_adapter=None,
            system_prompt=SYSTEM_PROMPT,
            learning_rate=plan["learning_rate"],
            gradient_accumulation=plan["gradient_accumulation"],
            staging_root=layout["staging_root"],
            final_root=layout["final_root"],
            load_model=True,
            expected_rows=256,
            max_steps=128,
            warmup_ratio=0.05,
        )
        report = {
            "schema_version": "mouth_recovery_v2_exact_nostep_preflight_v1",
            "experiment_id": EXPERIMENT_ID,
            "recorded_utc": utc(),
            "pass": True,
            "run_authorized": False,
            "training_authorized": False,
            "optimizer_rows": len(prepared["encoded"]),
            "optimizer_steps_configured": 128,
            "optimizer_steps_executed": 0,
            "forward_executed": False,
            "backward_executed": False,
            "optimizer_step_executed": False,
            "lease_begin_run_called": False,
            "precision": "bf16",
            "learning_rate": plan["learning_rate"],
            "gradient_accumulation": plan["gradient_accumulation"],
            "lora_coverage": prepared["coverage"],
            "train_sha256": sha256(TRAIN),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    finally:
        if prepared is not None:
            for key in ("optimizer", "model", "tokenizer"):
                if prepared.get(key) is not None:
                    del prepared[key]
        gc.collect()
        torch.cuda.empty_cache()
    write_new(ROOT / "EXACT_RUNTIME_NOSTEP_PREFLIGHT.json", report)
    return report


def authorize_once() -> dict:
    plan_path = ROOT / "campaign_plan.json"
    status_path = ROOT / "STATUS.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    preflight = json.loads((ROOT / "EXACT_RUNTIME_NOSTEP_PREFLIGHT.json").read_text(encoding="utf-8"))
    if plan["run_authorized"] is not False or plan["training_authorized"] is not False:
        raise ValueError("authorize_requires_closed_plan")
    if preflight.get("pass") is not True or preflight.get("optimizer_steps_executed") != 0:
        raise ValueError("authorize_requires_passing_nostep")
    out_root = Path(plan["checkpoint_paths"]["run_root"])
    if out_root.exists():
        raise ValueError(f"output_root_exists:{out_root}")
    token_path = canary.named_authorization_path(EXPERIMENT_ID)
    if token_path.exists():
        raise FileExistsError(f"token_exists:{token_path}")
    now = utc()
    authorized = dict(plan)
    authorized.update({"run_authorized": True, "training_authorized": False, "status": "RUN_AUTHORIZED_AWAITING_CONSUME", "authorized_at": now})
    staged = plan_path.with_suffix(".authorize_stage")
    staged.write_text(json.dumps(authorized, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    plan_sha = sha256(staged)
    token = {
        "schema_version": canary.NAMED_UNLOCK_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "plan_sha256": plan_sha,
        "status": "issued",
        "issued_at": now,
        "issued_by": "mouth_recovery_v2_authorize_once",
    }
    token_path.parent.mkdir(parents=True, exist_ok=True)
    staged_token = token_path.with_suffix(".authorize_stage")
    staged_token.write_text(json.dumps(token, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(str(staged), str(plan_path))
    os.replace(str(staged_token), str(token_path))
    status = {"experiment_id": EXPERIMENT_ID, "status": authorized["status"], "implementation_authorized": True, "run_authorized": True, "training_authorized": False, "campaign_plan_sha256": sha256(plan_path), "campaign_root": str(ROOT).replace("\\", "/")}
    status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"plan_sha256": sha256(plan_path), "run_authorized": True, "training_authorized": False, "token_path": str(token_path)}


def execute_once() -> dict:
    plan_path = ROOT / "campaign_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("run_authorized") is not True or plan.get("training_authorized") is not False:
        raise ValueError("run_not_authorized")
    plan_sha = sha256(plan_path)
    consumed = canary.consume_named_hard_stop_authorization(experiment_id=EXPERIMENT_ID, plan_sha256=plan_sha)
    result: dict = {"schema_version": "mouth_recovery_v2_run_result_v1", "experiment_id": EXPERIMENT_ID, "started_utc": utc(), "token_consumed": True, "token": consumed, "ok": False, "deployment_changed": False}
    try:
        train_sha = sha256(TRAIN)
        parent_sha = sha256(PARENT / "config.json")
        result["training"] = trainer.train_targeted_patch_16_single_lease(
            train_jsonl=TRAIN,
            parent_adapter=None,
            system_prompt=SYSTEM_PROMPT,
            run_id=EXPERIMENT_ID,
            learning_rate=float(plan["learning_rate"]),
            max_steps=128,
            checkpoint_steps=(32, 64, 96, 128),
            expected_rows=256,
            warmup_ratio=0.05,
        )
        result["ok"] = bool(result["training"].get("ok"))
        result["train_sha256"] = train_sha
        result["parent_config_sha256"] = parent_sha
        result["finished_utc"] = utc()
        return result
    finally:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["run_authorized"] = False
        plan["training_authorized"] = False
        plan["status"] = "REARMED_RUN_UNAUTHORIZED"
        plan["rearmed_at"] = utc()
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        (ROOT / "STATUS.json").write_text(json.dumps({"experiment_id": EXPERIMENT_ID, "status": plan["status"], "implementation_authorized": True, "run_authorized": False, "training_authorized": False, "campaign_plan_sha256": sha256(plan_path)}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        result_path = ROOT / "FINAL_RUN_RESULT.json"
        if not result_path.exists():
            result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("install-preflight", "authorize", "run"))
    args = parser.parse_args()
    if args.mode == "install-preflight":
        print(json.dumps(install(), indent=2, sort_keys=True))
        print(json.dumps(exact_nostep_preflight(), indent=2, sort_keys=True))
    elif args.mode == "authorize":
        print(json.dumps(authorize_once(), indent=2, sort_keys=True))
    else:
        print(json.dumps(execute_once(), indent=2, sort_keys=True, default=str))
