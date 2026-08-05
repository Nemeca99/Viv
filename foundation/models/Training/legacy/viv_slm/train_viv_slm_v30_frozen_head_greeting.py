#!/usr/bin/env python3
"""Train a frozen-baseline, greeting-only Viv-SLM correction canary.

This is deliberately a separate lane from the V28 incumbent.  The V28
transformer representation is loaded and frozen; only the output head is
trainable, and the loss includes replay-preservation penalties against the
frozen parent.  The resulting checkpoint is an offline renderer candidate,
not a replacement for V28 and not a CPU authority.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

import torch
from torch.nn import functional as F

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
SCRIPT_ROOT = FOUNDATION / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import train_viv_slm_identity_v1 as base  # noqa: E402

BASE_INPUT_ROOT = (
    VIV_ROOT / "models" / "viv_slm_identity_personality_v28_canonical_disambiguation" / "inputs"
)
FOCUS_INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v29_greeting_focus" / "inputs"
PARENT_CHECKPOINT = (
    VIV_ROOT
    / "models"
    / "viv_slm_identity_personality_v28_canonical_disambiguation"
    / "runs"
    / "canonical_disambiguation_steps_0250"
    / "checkpoint.pt"
)
DEFAULT_OUTPUT = (
    VIV_ROOT
    / "models"
    / "viv_slm_identity_personality_v30_frozen_head_greeting"
    / "runs"
    / "frozen_head_correction_steps_0250"
)
STEP_INCREMENT = 250
TRAINABLE_PARAMETER_NAMES = ("lm_head.weight", "lm_head.bias")
FOCUS_VIEW = "v29_greeting_only_focus"
EXPECTED_PARENT_CHECKPOINT_SHA256 = "99D536EE2E0AB804B70B54B4C81C617468564F825EAE82E2F6296964796C1BF0"


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _load_masked_shard(
    path: Path,
    *,
    vocab_size: int,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or payload.get("schema_version") not in base.MASKED_TENSOR_SCHEMAS:
        raise ValueError(f"v30_focus_tensor_schema_mismatch:{path}")
    inputs = payload.get("inputs")
    targets = payload.get("targets")
    loss_mask = payload.get("loss_mask")
    if not all(isinstance(value, torch.Tensor) for value in (inputs, targets, loss_mask)):
        raise ValueError(f"v30_focus_tensor_missing:{path}")
    if inputs.shape != targets.shape or loss_mask.shape != inputs.shape:
        raise ValueError(f"v30_focus_tensor_shape_mismatch:{path}")
    if inputs.ndim != 2 or loss_mask.dtype != torch.bool:
        raise ValueError(f"v30_focus_tensor_dtype_mismatch:{path}")
    if inputs.numel() and (
        int(inputs.min()) < 0
        or int(inputs.max()) >= vocab_size
        or int(targets.min()) < 0
        or int(targets.max()) >= vocab_size
    ):
        raise ValueError(f"v30_focus_tensor_token_range_mismatch:{path}")
    return (
        inputs.to(dtype=torch.long),
        targets.to(dtype=torch.long),
        loss_mask,
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"v30_json_object_required:{path}")
    return value


def validate_sources() -> dict[str, Any]:
    """Validate the frozen parent and identify the single greeting focus shard."""
    base_tokenizer, base_manifest, base_tensor_dir = base._validate_input(BASE_INPUT_ROOT)
    focus_tokenizer, focus_manifest, focus_tensor_dir = base._validate_input(FOCUS_INPUT_ROOT)
    if base_tokenizer.vocab_sha256 != focus_tokenizer.vocab_sha256:
        raise ValueError("v30_parent_focus_vocab_hash_mismatch")
    if base_manifest.get("validation_unchanged_from_v17") is not True:
        raise ValueError("v30_parent_validation_contract_missing")
    if focus_manifest.get("base_replay") != "v28_canonical_disambiguation_unchanged":
        raise ValueError("v30_focus_parent_replay_contract_missing")
    if focus_manifest.get("training_authorized") is not False or focus_manifest.get("run_authorized") is not False:
        raise ValueError("v30_focus_input_authority_flags_not_closed")
    if not PARENT_CHECKPOINT.is_file():
        raise FileNotFoundError(f"v30_parent_checkpoint_missing:{PARENT_CHECKPOINT}")
    parent_sha256 = _sha256(PARENT_CHECKPOINT)
    if parent_sha256 != EXPECTED_PARENT_CHECKPOINT_SHA256:
        raise ValueError(f"v30_parent_checkpoint_hash_mismatch:{parent_sha256}")

    tensor_manifest = _read_json(FOCUS_INPUT_ROOT / "tensor_dataset" / "MANIFEST.json")
    train_shards = tensor_manifest.get("splits", {}).get("train", {}).get("shards", [])
    focus_shards = [
        row for row in train_shards
        if isinstance(row, Mapping) and row.get("view") == FOCUS_VIEW
    ]
    if len(focus_shards) != 1:
        raise ValueError(f"v30_focus_shard_count:{len(focus_shards)}")
    focus_shard_path = focus_tensor_dir / str(focus_shards[0]["path"]).replace("/", "\\")
    if not focus_shard_path.is_file():
        raise FileNotFoundError(f"v30_focus_shard_missing:{focus_shard_path}")
    focus_inputs, focus_targets, focus_masks = _load_masked_shard(
        focus_shard_path,
        vocab_size=focus_tokenizer.vocab_size,
    )
    if focus_inputs.shape[0] != int(focus_shards[0].get("examples") or 0):
        raise ValueError("v30_focus_shard_example_count_mismatch")
    return {
        "base_tokenizer": base_tokenizer,
        "base_manifest": base_manifest,
        "base_tensor_dir": base_tensor_dir,
        "focus_manifest": focus_manifest,
        "focus_tensor_dir": focus_tensor_dir,
        "focus_shard": focus_shard_path,
        "focus_shard_manifest": focus_shards[0],
        "focus_inputs": focus_inputs,
        "focus_targets": focus_targets,
        "focus_masks": focus_masks,
        "parent_checkpoint_sha256": parent_sha256,
    }


def _masked_cross_entropy(
    logits: torch.Tensor,
    targets: torch.Tensor,
    loss_mask: torch.Tensor,
) -> torch.Tensor:
    valid = loss_mask.reshape(-1).bool()
    if not bool(valid.any()):
        raise ValueError("v30_batch_contains_no_response_targets")
    return F.cross_entropy(
        logits.reshape(-1, logits.shape[-1])[valid],
        targets.reshape(-1)[valid],
    )


def _mean_squared_logit_drift(current: torch.Tensor, reference: torch.Tensor) -> torch.Tensor:
    return F.mse_loss(current.float(), reference.float())


def _load_parent_model(
    *,
    vocab_size: int,
    device: torch.device,
) -> tuple[base.TransformerLanguageModel, dict[str, Any]]:
    checkpoint = torch.load(PARENT_CHECKPOINT, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict):
        raise ValueError("v30_parent_checkpoint_object_required")
    if checkpoint.get("schema_version") != base.CHECKPOINT_SCHEMA:
        raise ValueError("v30_parent_checkpoint_schema_mismatch")
    if checkpoint.get("weights_status") != "trained":
        raise ValueError("v30_parent_checkpoint_not_trained")
    if checkpoint.get("vocab_size") != vocab_size:
        raise ValueError("v30_parent_checkpoint_vocab_size_mismatch")
    if checkpoint.get("model_config") != base.MODEL_CONFIG:
        raise ValueError("v30_parent_checkpoint_model_config_mismatch")
    model = base._make_model(vocab_size, device=device)
    state_dict = checkpoint.get("model_state_dict")
    if not isinstance(state_dict, Mapping):
        raise ValueError("v30_parent_checkpoint_state_missing")
    model.load_state_dict(state_dict, strict=True)
    return model, checkpoint


def _parameter_scope(model: torch.nn.Module) -> tuple[list[torch.nn.Parameter], dict[str, bool]]:
    trainable: list[torch.nn.Parameter] = []
    scope: dict[str, bool] = {}
    for name, parameter in model.named_parameters():
        allowed = name in TRAINABLE_PARAMETER_NAMES
        parameter.requires_grad_(allowed)
        scope[name] = allowed
        if allowed:
            trainable.append(parameter)
    if tuple(name for name, allowed in scope.items() if allowed) != TRAINABLE_PARAMETER_NAMES:
        raise ValueError(f"v30_trainable_scope_mismatch:{scope}")
    return trainable, scope


def _parameter_deltas(
    model: torch.nn.Module,
    reference: torch.nn.Module,
) -> dict[str, float | int]:
    max_delta = 0.0
    l2 = 0.0
    changed_tensors = 0
    for name, current in model.state_dict().items():
        original = reference.state_dict()[name]
        delta = (current.detach().float().cpu() - original.detach().float().cpu()).abs()
        tensor_max = float(delta.max()) if delta.numel() else 0.0
        if tensor_max > 0.0:
            changed_tensors += 1
        max_delta = max(max_delta, tensor_max)
        l2 += float(delta.pow(2).sum())
    return {
        "max_abs_delta": max_delta,
        "l2_delta": math.sqrt(l2),
        "changed_tensors": changed_tensors,
    }


def _anchor_drift(
    model: base.TransformerLanguageModel,
    reference: base.TransformerLanguageModel,
    inputs: torch.Tensor,
    *,
    device: torch.device,
) -> float:
    model.eval()
    reference.eval()
    with torch.no_grad():
        current = model(inputs.to(device))
        original = reference(inputs.to(device))
    return float(_mean_squared_logit_drift(current, original))


def train(
    *,
    output_dir: Path = DEFAULT_OUTPUT,
    steps: int = STEP_INCREMENT,
    learning_rate: float = 0.00001,
    anchor_weight: float = 5.0,
    prompt_weight: float = 5.0,
    batch_size: int = 32,
    anchor_batch_size: int = 64,
    seed: int = 4242,
    device_name: str = "cuda",
    authorize: bool = False,
) -> dict[str, Any]:
    if not authorize:
        raise PermissionError("v30_late_correction_requires_explicit_authorize_flag")
    if steps <= 0 or steps % STEP_INCREMENT != 0:
        raise ValueError("v30_steps_must_be_positive_multiple_of_250")
    if learning_rate <= 0 or anchor_weight < 0 or prompt_weight < 0:
        raise ValueError("v30_optimizer_or_preservation_parameter_invalid")
    if batch_size <= 0 or anchor_batch_size <= 0:
        raise ValueError("v30_batch_size_invalid")
    if output_dir.exists():
        raise FileExistsError(f"v30_output_exists_refuse_overwrite:{output_dir}")
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("v30_cuda_requested_but_unavailable")

    source = validate_sources()
    tokenizer = source["base_tokenizer"]
    base_train_inputs, base_train_targets, base_train_masks = base._load_split(
        source["base_tensor_dir"],
        "train",
        vocab_size=tokenizer.vocab_size,
        response_only_loss=True,
    )
    validation_inputs, validation_targets, validation_masks = base._load_split(
        source["base_tensor_dir"],
        "validation",
        vocab_size=tokenizer.vocab_size,
        response_only_loss=True,
    )
    if base_train_masks is None or validation_masks is None:
        raise ValueError("v30_response_only_masks_required")

    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
    model, parent_checkpoint = _load_parent_model(
        vocab_size=tokenizer.vocab_size,
        device=device,
    )
    reference = deepcopy(model).to(device)
    reference.eval()
    for parameter in reference.parameters():
        parameter.requires_grad_(False)
    trainable_parameters, parameter_scope = _parameter_scope(model)
    model.eval()  # frozen features; no dropout noise in this correction lane
    optimizer = torch.optim.AdamW(trainable_parameters, lr=learning_rate)
    focus_inputs = source["focus_inputs"]
    focus_targets = source["focus_targets"]
    focus_masks = source["focus_masks"]
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed + 100)
    history: list[dict[str, Any]] = []

    for step in range(1, steps + 1):
        focus_indices = torch.randint(
            0,
            focus_inputs.shape[0],
            (min(batch_size, focus_inputs.shape[0]),),
            generator=generator,
        )
        anchor_indices = torch.randint(
            0,
            base_train_inputs.shape[0],
            (min(anchor_batch_size, base_train_inputs.shape[0]),),
            generator=generator,
        )
        batch_focus_inputs = focus_inputs[focus_indices].to(device)
        batch_focus_targets = focus_targets[focus_indices].to(device)
        batch_focus_masks = focus_masks[focus_indices].to(device)
        batch_anchor_inputs = base_train_inputs[anchor_indices].to(device)
        optimizer.zero_grad(set_to_none=True)
        focus_logits = model(batch_focus_inputs)
        focus_nll = _masked_cross_entropy(
            focus_logits,
            batch_focus_targets,
            batch_focus_masks,
        )
        with torch.no_grad():
            reference_focus_logits = reference(batch_focus_inputs)
            reference_anchor_logits = reference(batch_anchor_inputs)
        prompt_mask = ~batch_focus_masks.reshape(-1).bool()
        prompt_current = focus_logits.reshape(-1, tokenizer.vocab_size)[prompt_mask]
        prompt_reference = reference_focus_logits.reshape(-1, tokenizer.vocab_size)[prompt_mask]
        prompt_drift = _mean_squared_logit_drift(prompt_current, prompt_reference)
        anchor_current = model(batch_anchor_inputs)
        anchor_drift = _mean_squared_logit_drift(anchor_current, reference_anchor_logits)
        loss = focus_nll + (prompt_weight * prompt_drift) + (anchor_weight * anchor_drift)
        loss.backward()
        grad_norm_before = float(torch.nn.utils.clip_grad_norm_(trainable_parameters, max_norm=1.0))
        grad_norm_after = math.sqrt(
            sum(
                float(parameter.grad.detach().float().pow(2).sum())
                for parameter in trainable_parameters
                if parameter.grad is not None
            )
        )
        optimizer.step()

        if step % STEP_INCREMENT != 0:
            continue
        model.eval()
        training_metrics = base._evaluate(
            model,
            base_train_inputs,
            base_train_targets,
            device=device,
            batch_size=64,
            loss_masks=base_train_masks,
        )
        validation_metrics = base._evaluate(
            model,
            validation_inputs,
            validation_targets,
            device=device,
            batch_size=64,
            loss_masks=validation_masks,
        )
        focus_metrics = base._evaluate(
            model,
            focus_inputs,
            focus_targets,
            device=device,
            batch_size=64,
            loss_masks=focus_masks,
        )
        record = {
            "step": step,
            "training": training_metrics,
            "validation": validation_metrics,
            "focus": focus_metrics,
            "focus_loss_last_batch": float(focus_nll.detach().cpu()),
            "prompt_preservation_loss_last_batch": float(prompt_drift.detach().cpu()),
            "anchor_preservation_loss_last_batch": float(anchor_drift.detach().cpu()),
            "grad_norm_before_clip": grad_norm_before,
            "grad_norm_after_clip": grad_norm_after,
            "anchor_logit_mse_fixed_probe": _anchor_drift(
                model,
                reference,
                base_train_inputs[: min(256, base_train_inputs.shape[0])],
                device=device,
            ),
            "parameter_deltas": _parameter_deltas(model, reference),
        }
        history.append(record)
        print(json.dumps(record, sort_keys=True))

    model.eval()
    parent_sample = base._sample(
        reference,
        tokenizer,
        device=device,
        temperature=0.0,
        top_k=40,
        max_new_tokens=160,
        seed=seed + 100,
        stop_marker="<END>",
    )
    correction_sample = base._sample(
        model,
        tokenizer,
        device=device,
        temperature=0.0,
        top_k=40,
        max_new_tokens=160,
        seed=seed + 100,
        stop_marker="<END>",
    )
    final = history[-1]
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "schema_version": base.CHECKPOINT_SCHEMA,
        "model": base.MODEL_NAME,
        "weights_status": "trained",
        "training_steps": steps,
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "model_config": base.MODEL_CONFIG,
        "seed": seed,
        "starting_sample": parent_sample,
        "best_validation_step": steps,
        "best_validation_nll": final["validation"]["nll"],
        "best_model_state_dict": base._cpu_state_dict(model),
        "model_state_dict": base._cpu_state_dict(model),
        "optimizer_state_dict": optimizer.state_dict(),
        "training_history": history,
        "training_config": {
            "objective": "frozen_v28_greeting_head_correction",
            "initialization": "warm_start_v28_frozen_representation",
            "parent_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
            "parent_checkpoint_sha256": source["parent_checkpoint_sha256"],
            "focus_input_root": str(FOCUS_INPUT_ROOT).replace("\\", "/"),
            "focus_shard": str(source["focus_shard"]).replace("\\", "/"),
            "focus_view": FOCUS_VIEW,
            "trainable_parameter_names": list(TRAINABLE_PARAMETER_NAMES),
            "parameter_scope": parameter_scope,
            "learning_rate": learning_rate,
            "anchor_preservation_weight": anchor_weight,
            "prompt_preservation_weight": prompt_weight,
            "gradient_clip_norm": 1.0,
            "batch_size": batch_size,
            "anchor_batch_size": anchor_batch_size,
            "step_increment": STEP_INCREMENT,
            "device": device_name,
            "response_only_loss": True,
        },
        "world_knowledge_included": False,
        "aios_live_mutation": False,
        "training_authorized": True,
        "run_authorized": True,
        "promotion_authorized": False,
        "deployment_changed": False,
    }
    checkpoint_path = output_dir / "checkpoint.pt"
    torch.save(checkpoint, checkpoint_path)
    _json_write(
        output_dir / "generation_comparison.json",
        {
            "parent_v28_sample": parent_sample,
            "correction_sample": correction_sample,
            "temperature": 0.0,
            "top_k": 40,
        },
    )
    _json_write(output_dir / "training_history.json", {"measurements": history})
    run_manifest = {
        "schema_version": "viv_slm_v30_frozen_head_greeting_canary_run_v1",
        "status": "COMPLETE_OFFLINE_CANARY",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": base.MODEL_NAME,
        "checkpoint": str(checkpoint_path).replace("\\", "/"),
        "checkpoint_sha256": _sha256(checkpoint_path),
        "parent_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
        "parent_checkpoint_sha256": source["parent_checkpoint_sha256"],
        "focus_shard": str(source["focus_shard"]).replace("\\", "/"),
        "focus_shard_sha256": _sha256(source["focus_shard"]),
        "steps": steps,
        "step_increment": STEP_INCREMENT,
        "parameter_scope": list(TRAINABLE_PARAMETER_NAMES),
        "frozen_parameter_count": sum(1 for allowed in parameter_scope.values() if not allowed),
        "training_result": final,
        "generation_comparison": {
            "path": str((output_dir / "generation_comparison.json")).replace("\\", "/"),
            "sha256": _sha256(output_dir / "generation_comparison.json"),
        },
        "input_contract": {
            "base_input_manifest_sha256": _sha256(BASE_INPUT_ROOT / "INPUT_MANIFEST.json"),
            "focus_input_manifest_sha256": _sha256(FOCUS_INPUT_ROOT / "INPUT_MANIFEST.json"),
            "validation_unchanged_from_v17": True,
            "world_knowledge_included": False,
            "response_only_loss": True,
        },
        "authority": {
            "training_authorized": True,
            "run_authorized": True,
            "promotion_authorized": False,
            "deployment_changed": False,
            "live_model_changed": False,
            "cpu_decision_authority": True,
            "renderer_authority": False,
        },
        "disposition": "HOLD_PENDING_FULL_V28_REPLAY_AND_CPU_BOUNDARY_REGRESSION",
        "next_action": "run_v30_full_behavioral_probes_and_cpu_router_surface_before_any_promotion",
    }
    _json_write(output_dir / "RUN_MANIFEST.json", run_manifest)
    (output_dir / "RUN_REPORT.md").write_text(
        "# Viv-SLM V30 frozen-head greeting correction canary\n\n"
        f"- Steps: {steps} (increment {STEP_INCREMENT})\n"
        f"- Parent: `{source['parent_checkpoint_sha256']}`\n"
        "- Trainable parameters: `lm_head.weight`, `lm_head.bias`\n"
        "- All transformer representation parameters frozen: true\n"
        f"- Final validation NLL: {final['validation']['nll']}\n"
        f"- Fixed-anchor logit MSE: {final['anchor_logit_mse_fixed_probe']}\n"
        "- Promotion/deployment: closed\n"
        "- CPU decision authority: preserved\n",
        encoding="utf-8",
        newline="\n",
    )
    run_manifest["run_report_sha256"] = _sha256(output_dir / "RUN_REPORT.md")
    _json_write(output_dir / "RUN_MANIFEST.json", run_manifest)
    return run_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--steps", type=int, default=STEP_INCREMENT)
    parser.add_argument("--learning-rate", type=float, default=0.00001)
    parser.add_argument("--anchor-weight", type=float, default=5.0)
    parser.add_argument("--prompt-weight", type=float, default=5.0)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--anchor-batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=4242)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    source = validate_sources()
    if args.dry_run:
        print(json.dumps({
            "status": "VIV_SLM_V30_FROZEN_HEAD_CANARY_PREFLIGHT_PASS",
            "parent_checkpoint_sha256": source["parent_checkpoint_sha256"],
            "focus_shard": str(source["focus_shard"]).replace("\\", "/"),
            "focus_examples": int(source["focus_inputs"].shape[0]),
            "trainable_parameter_names": list(TRAINABLE_PARAMETER_NAMES),
            "base_validation_unchanged_from_v17": True,
            "training_authorized": False,
            "run_authorized": False,
            "promotion_authorized": False,
        }, sort_keys=True))
        return 0
    result = train(
        output_dir=args.output_dir,
        steps=args.steps,
        learning_rate=args.learning_rate,
        anchor_weight=args.anchor_weight,
        prompt_weight=args.prompt_weight,
        batch_size=args.batch_size,
        anchor_batch_size=args.anchor_batch_size,
        seed=args.seed,
        device_name=args.device,
        authorize=args.authorize,
    )
    print(json.dumps({
        "status": "VIV_SLM_V30_FROZEN_HEAD_CANARY_COMPLETE",
        "checkpoint": result["checkpoint"],
        "checkpoint_sha256": result["checkpoint_sha256"],
        "steps": result["steps"],
        "disposition": result["disposition"],
        "promotion_authorized": result["authority"]["promotion_authorized"],
        "deployment_changed": result["authority"]["deployment_changed"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
