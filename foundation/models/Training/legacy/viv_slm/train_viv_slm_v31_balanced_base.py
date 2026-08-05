#!/usr/bin/env python3
"""Run the governed V31 balanced-base Viv-SLM training lane.

The underlying optimizer remains the existing verified character-level
trainer.  This wrapper adds the campaign-specific authority check, parent
checkpoint hash check, explicit authorization flag, and a durable authorization
receipt so the training command cannot be mistaken for a promotion or deploy.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import train_viv_slm_identity_v1 as base_trainer

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v31_balanced_base" / "inputs"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v31_balanced_base" / "runs" / "balanced_base_steps_0250"
PARENT_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v28_canonical_disambiguation" / "runs" / "canonical_disambiguation_steps_0250" / "checkpoint.pt"
CURRENT_TASK = FOUNDATION / "artifacts" / "auto" / "agentic" / "CURRENT_TASK.json"
PARENT_CHECKPOINT_SHA256 = "99D536EE2E0AB804B70B54B4C81C617468564F825EAE82E2F6296964796C1BF0"
CAMPAIGN_ID = "viv_slm_identity_personality_v31_balanced_base_0250"
STEP_INCREMENT = 250


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _require_authority(*, authorize: bool, parent_checkpoint: Path) -> dict[str, Any]:
    if not authorize:
        raise PermissionError("v31_balanced_base_requires_explicit_authorize_flag")
    if not CURRENT_TASK.is_file():
        raise FileNotFoundError(f"viv_v31_current_task_missing:{CURRENT_TASK}")
    task = json.loads(CURRENT_TASK.read_text(encoding="utf-8"))
    record = task.get("v31_balanced_base_training")
    if not isinstance(record, dict):
        raise PermissionError("v31_balanced_base_task_authorization_record_missing")
    if record.get("training_authorized") is not True or record.get("run_authorized") is not True:
        raise PermissionError("v31_balanced_base_task_authorization_closed")
    if record.get("promotion_authorized") is not False or record.get("deployment_changed") is not False:
        raise PermissionError("v31_balanced_base_promotion_or_deployment_state_invalid")
    resolved_parent = parent_checkpoint.resolve()
    if resolved_parent != PARENT_CHECKPOINT.resolve():
        raise ValueError(f"viv_v31_parent_checkpoint_mismatch:{resolved_parent}")
    if not parent_checkpoint.is_file():
        raise FileNotFoundError(f"viv_v31_parent_checkpoint_missing:{parent_checkpoint}")
    parent_hash = _sha256(parent_checkpoint)
    if parent_hash.casefold() != PARENT_CHECKPOINT_SHA256.casefold():
        raise ValueError(f"viv_v31_parent_checkpoint_hash_mismatch:{parent_hash}")
    return {
        "campaign_id": CAMPAIGN_ID,
        "task_updated_utc": str(task.get("updated_utc") or ""),
        "parent_checkpoint": str(parent_checkpoint).replace("\\", "/"),
        "parent_checkpoint_sha256": parent_hash,
        "training_authorized": True,
        "run_authorized": True,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
    }


def train(
    *,
    input_root: Path = INPUT_ROOT,
    output_dir: Path = DEFAULT_OUTPUT,
    parent_checkpoint: Path = PARENT_CHECKPOINT,
    steps: int = STEP_INCREMENT,
    batch_size: int = 64,
    eval_batch_size: int = 64,
    learning_rate: float = 0.0003,
    max_grad_norm: float = 1.0,
    seed: int = 42,
    device_name: str = "cuda",
    sample_tokens: int = 160,
    top_k: int = 40,
    authorize: bool = False,
) -> dict[str, Any]:
    if steps <= 0 or steps % STEP_INCREMENT != 0:
        raise ValueError("viv_v31_steps_must_be_positive_multiple_of_250")
    authority = _require_authority(authorize=authorize, parent_checkpoint=parent_checkpoint)
    input_manifest = json.loads((input_root / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    if input_manifest.get("schema_version") != "viv_slm_v31_balanced_base_inputs_v1":
        raise ValueError("viv_v31_input_schema_mismatch")
    if input_manifest.get("world_knowledge_included") is not False or input_manifest.get("response_only_loss") is not True:
        raise ValueError("viv_v31_input_policy_mismatch")
    result = base_trainer.train(
        input_root=input_root,
        output_dir=output_dir,
        steps=steps,
        warm_start=parent_checkpoint,
        batch_size=batch_size,
        eval_batch_size=eval_batch_size,
        learning_rate=learning_rate,
        max_grad_norm=max_grad_norm,
        seed=seed,
        device_name=device_name,
        sample_tokens=sample_tokens,
        top_k=top_k,
    )
    run_manifest_path = output_dir / "RUN_MANIFEST.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    run_manifest.update(
        {
            "campaign_id": CAMPAIGN_ID,
            "governance": authority,
            "parent_checkpoint": authority["parent_checkpoint"],
            "parent_checkpoint_sha256": authority["parent_checkpoint_sha256"],
            "training_authorized": True,
            "run_authorized": True,
            "promotion_authorized": False,
            "deployment_changed": False,
            "live_model_changed": False,
            "next_step": "run_matched_v15_and_legacy_probes_then_compare_pareto_metrics_before_any_promotion",
        }
    )
    _json_write(run_manifest_path, run_manifest)
    _json_write(
        output_dir / "AUTHORIZATION.json",
        {
            "schema_version": "viv_slm_v31_training_authorization_v1",
            "campaign_id": CAMPAIGN_ID,
            "authorized_utc": authority["task_updated_utc"],
            "input_manifest": str(input_root / "INPUT_MANIFEST.json").replace("\\", "/"),
            "input_manifest_sha256": _sha256(input_root / "INPUT_MANIFEST.json"),
            "parent_checkpoint": authority["parent_checkpoint"],
            "parent_checkpoint_sha256": authority["parent_checkpoint_sha256"],
            "steps": steps,
            "step_increment": STEP_INCREMENT,
            "training_authorized": True,
            "run_authorized": True,
            "promotion_authorized": False,
            "deployment_changed": False,
            "live_model_changed": False,
        },
    )
    return run_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=INPUT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--parent-checkpoint", type=Path, default=PARENT_CHECKPOINT)
    parser.add_argument("--steps", type=int, default=STEP_INCREMENT)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--eval-batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.0003)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--sample-tokens", type=int, default=160)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--authorize", action="store_true")
    args = parser.parse_args(argv)
    result = train(
        input_root=args.input_root,
        output_dir=args.output_dir,
        parent_checkpoint=args.parent_checkpoint,
        steps=args.steps,
        batch_size=args.batch_size,
        eval_batch_size=args.eval_batch_size,
        learning_rate=args.learning_rate,
        max_grad_norm=args.max_grad_norm,
        seed=args.seed,
        device_name=args.device,
        sample_tokens=args.sample_tokens,
        top_k=args.top_k,
        authorize=args.authorize,
    )
    print(
        json.dumps(
            {
                "status": "VIV_SLM_V31_BALANCED_BASE_TRAINING_COMPLETE",
                "campaign_id": CAMPAIGN_ID,
                "checkpoint": result["checkpoint"],
                "training_steps": result["training_steps"],
                "best_validation_nll": result["best_validation_nll"],
                "training_authorized": result["training_authorized"],
                "run_authorized": result["run_authorized"],
                "promotion_authorized": result["promotion_authorized"],
                "deployment_changed": result["deployment_changed"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
