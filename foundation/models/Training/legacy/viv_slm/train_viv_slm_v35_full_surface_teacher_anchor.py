#!/usr/bin/env python3
"""Run one bounded V35 full-surface teacher-anchor Viv-SLM canary.

V35 tests one broad hypothesis after the targeted V34 branch: retain V32 as
the metric working parent, train on the complete V31 balanced response-only
stream, and add a frozen V28 behavior-reference KL anchor to every replay
batch.  The objective is intentionally simple and explicit.  A bounded
controller adjusts anchor pressure and learning-rate scale from measured
teacher divergence and validation drift; a guarded rollback restores the last
accepted state and resets the optimizer after a guard failure.  The candidate
is always emitted as a new immutable layer and never promotes or deploys.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from typing import Any

import torch
from torch.nn import functional as F

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
SCRIPT_ROOT = FOUNDATION / "scripts"
MODEL_ROOT = VIV_ROOT / "models" / "uml_bigram_part3"
for path in (FOUNDATION, SCRIPT_ROOT, VIV_ROOT, MODEL_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import train_viv_slm_identity_v1 as base  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v31_balanced_base" / "inputs"
PARENT_CHECKPOINT = (
    VIV_ROOT
    / "models"
    / "viv_slm_identity_personality_v32_balanced_low_lr"
    / "runs"
    / "balanced_low_lr_steps_0250"
    / "checkpoint.pt"
)
BEHAVIOR_REFERENCE_CHECKPOINT = (
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
    / "viv_slm_identity_personality_v35_full_surface_teacher_anchor"
    / "runs"
    / "full_surface_teacher_anchor_steps_0250"
)
CURRENT_TASK = FOUNDATION / "artifacts" / "auto" / "agentic" / "CURRENT_TASK.json"

INPUT_SCHEMA_VERSION = "viv_slm_v31_balanced_base_inputs_v1"
INPUT_MANIFEST_SHA256 = "18446924D85E554A1D6452F011F88798CC4948D8D66CC021165C0B25F9953D72"
VOCAB_FILE_SHA256 = "00982C5992060D4D55E4843D0726A9823CCB71C46E04FC9E9DFFBCDB1D3F8179"
TENSOR_MANIFEST_SHA256 = "23C6B5B8C4C5B9341847285B2FF5C200800B40AC7A1D9655A82BCBBBD5A24B6E"
PARENT_CHECKPOINT_SHA256 = "EC7065B19C6630B7CF3DD64AE78FD92371A02A4A4E7465EF3206AB6CE30EE2F9"
BEHAVIOR_REFERENCE_CHECKPOINT_SHA256 = "99D536EE2E0AB804B70B54B4C81C617468564F825EAE82E2F6296964796C1BF0"
STEP_INCREMENT = 250
EVAL_INTERVAL = 50
LEARNING_RATE = 0.0001
SFT_WEIGHT = 1.0
BASE_ANCHOR_WEIGHT = 0.20
MIN_ANCHOR_WEIGHT = 0.05
MAX_ANCHOR_WEIGHT = 0.50
MIN_LR_SCALE = 0.20
MAX_LR_SCALE = 1.05
CONTROLLER_ALPHA = 0.10
TARGET_TEACHER_KL_DELTA = 0.002
TARGET_VALIDATION_NLL_DELTA = 0.001
VALIDATION_NLL_TOLERANCE = 0.001
VALIDATION_ACCURACY_TOLERANCE = 0.0005
TEACHER_KL_TOLERANCE = 0.002
MAX_CONSECUTIVE_GUARD_FAILURES = 2
CAMPAIGN_ID = "viv_slm_identity_personality_v35_full_surface_teacher_anchor_0250"


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


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"viv_v35_expected_json_object:{path}")
    return value


def _validate_authority(*, authorize: bool, steps: int, learning_rate: float) -> dict[str, Any]:
    if not authorize:
        raise PermissionError("v35_full_surface_teacher_anchor_requires_explicit_authorize_flag")
    if not CURRENT_TASK.is_file():
        raise FileNotFoundError(f"viv_v35_current_task_missing:{CURRENT_TASK}")
    task = _read_json(CURRENT_TASK)
    record = task.get("v35_full_surface_teacher_anchor_training")
    if not isinstance(record, dict):
        raise PermissionError("v35_full_surface_teacher_anchor_task_authorization_record_missing")
    if record.get("training_authorized") is not True or record.get("run_authorized") is not True:
        raise PermissionError("v35_full_surface_teacher_anchor_task_authorization_closed")
    if record.get("promotion_authorized") is not False or record.get("deployment_changed") is not False:
        raise PermissionError("v35_full_surface_teacher_anchor_promotion_or_deployment_state_invalid")
    if record.get("working_parent_layer_id") != "viv_v32_metric_progress_parent":
        raise PermissionError("v35_full_surface_teacher_anchor_working_parent_layer_invalid")
    if record.get("behavior_reference_layer_id") != "viv_v28_canonical_behavior_reference":
        raise PermissionError("v35_full_surface_teacher_anchor_behavior_reference_layer_invalid")
    scope = record.get("scope")
    if not isinstance(scope, dict) or int(scope.get("steps", -1)) != steps:
        raise PermissionError("v35_full_surface_teacher_anchor_scope_steps_invalid")
    if not math.isclose(float(scope.get("learning_rate", -1.0)), learning_rate, rel_tol=0.0, abs_tol=1e-12):
        raise PermissionError("v35_full_surface_teacher_anchor_scope_learning_rate_invalid")
    if str(record.get("parent_checkpoint_sha256") or "").casefold() != PARENT_CHECKPOINT_SHA256.casefold():
        raise PermissionError("v35_full_surface_teacher_anchor_parent_authority_hash_invalid")
    if str(record.get("behavior_reference_checkpoint_sha256") or "").casefold() != BEHAVIOR_REFERENCE_CHECKPOINT_SHA256.casefold():
        raise PermissionError("v35_full_surface_teacher_anchor_behavior_authority_hash_invalid")
    return {
        "campaign_id": CAMPAIGN_ID,
        "task_updated_utc": str(task.get("updated_utc") or ""),
        "working_parent_layer_id": record["working_parent_layer_id"],
        "behavior_reference_layer_id": record["behavior_reference_layer_id"],
        "parent_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
        "parent_checkpoint_sha256": PARENT_CHECKPOINT_SHA256,
        "behavior_reference_checkpoint": str(BEHAVIOR_REFERENCE_CHECKPOINT).replace("\\", "/"),
        "behavior_reference_checkpoint_sha256": BEHAVIOR_REFERENCE_CHECKPOINT_SHA256,
        "training_authorized": True,
        "run_authorized": True,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
    }


def _validate_sources() -> tuple[CharacterTokenizer, dict[str, Any], Path, dict[str, Any]]:
    input_manifest_path = INPUT_ROOT / "INPUT_MANIFEST.json"
    vocab_path = INPUT_ROOT / "VOCAB.json"
    tensor_manifest_path = INPUT_ROOT / "tensor_dataset" / "MANIFEST.json"
    for path in (input_manifest_path, vocab_path, tensor_manifest_path, PARENT_CHECKPOINT, BEHAVIOR_REFERENCE_CHECKPOINT):
        if not path.is_file():
            raise FileNotFoundError(f"viv_v35_source_missing:{path}")
    input_manifest = _read_json(input_manifest_path)
    if input_manifest.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise ValueError("viv_v35_input_schema_mismatch")
    if input_manifest.get("world_knowledge_included") is not False:
        raise ValueError("viv_v35_input_world_knowledge_policy_violation")
    if input_manifest.get("response_only_loss") is not True:
        raise ValueError("viv_v35_input_response_only_policy_mismatch")
    if input_manifest.get("training_authorized") is not False or input_manifest.get("run_authorized") is not False:
        raise ValueError("viv_v35_input_authority_flags_changed")
    expected = {
        input_manifest_path: INPUT_MANIFEST_SHA256,
        vocab_path: VOCAB_FILE_SHA256,
        tensor_manifest_path: TENSOR_MANIFEST_SHA256,
        PARENT_CHECKPOINT: PARENT_CHECKPOINT_SHA256,
        BEHAVIOR_REFERENCE_CHECKPOINT: BEHAVIOR_REFERENCE_CHECKPOINT_SHA256,
    }
    for path, expected_hash in expected.items():
        actual = _sha256(path)
        if actual.casefold() != expected_hash.casefold():
            raise ValueError(f"viv_v35_source_hash_mismatch:{path}:{actual}")
    tokenizer, validated_manifest, tensor_dir = base._validate_input(INPUT_ROOT)
    if validated_manifest != input_manifest:
        raise ValueError("viv_v35_input_manifest_read_mismatch")
    return tokenizer, input_manifest, tensor_dir, {
        "input_manifest": str(input_manifest_path).replace("\\", "/"),
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "vocab": str(vocab_path).replace("\\", "/"),
        "vocab_file_sha256": VOCAB_FILE_SHA256,
        "tensor_manifest": str(tensor_manifest_path).replace("\\", "/"),
        "tensor_manifest_sha256": TENSOR_MANIFEST_SHA256,
        "parent_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
        "parent_checkpoint_sha256": PARENT_CHECKPOINT_SHA256,
        "behavior_reference_checkpoint": str(BEHAVIOR_REFERENCE_CHECKPOINT).replace("\\", "/"),
        "behavior_reference_checkpoint_sha256": BEHAVIOR_REFERENCE_CHECKPOINT_SHA256,
        "schema_version": INPUT_SCHEMA_VERSION,
        "world_knowledge_included": False,
    }


def _masked_nll(logits: torch.Tensor, targets: torch.Tensor, masks: torch.Tensor) -> torch.Tensor:
    valid = masks.reshape(-1).bool()
    if not bool(valid.any()):
        raise ValueError("viv_v35_response_mask_empty")
    return F.cross_entropy(logits.reshape(-1, logits.shape[-1])[valid], targets.reshape(-1)[valid])


def _teacher_anchor_kl(
    student_logits: torch.Tensor,
    teacher_logits: torch.Tensor,
    masks: torch.Tensor,
) -> torch.Tensor:
    valid = masks.reshape(-1).bool()
    if not bool(valid.any()):
        raise ValueError("viv_v35_teacher_anchor_mask_empty")
    student_log_probs = F.log_softmax(student_logits.float().reshape(-1, student_logits.shape[-1])[valid], dim=-1)
    teacher_probs = F.softmax(teacher_logits.float().reshape(-1, teacher_logits.shape[-1])[valid], dim=-1)
    return F.kl_div(student_log_probs, teacher_probs, reduction="batchmean")


def _evaluate_teacher_alignment(
    student: torch.nn.Module,
    teacher: torch.nn.Module,
    inputs: torch.Tensor,
    masks: torch.Tensor,
    *,
    device: torch.device,
    batch_size: int,
) -> dict[str, float | int]:
    was_training = student.training
    student.eval()
    teacher.eval()
    total_kl = 0.0
    total_tokens = 0
    with torch.no_grad():
        for start in range(0, inputs.shape[0], batch_size):
            batch_inputs = inputs[start : start + batch_size].to(device)
            batch_masks = masks[start : start + batch_size].to(device).reshape(-1).bool()
            if not bool(batch_masks.any()):
                continue
            student_logits = student(batch_inputs).float().reshape(-1, student.vocab_size)[batch_masks]
            teacher_logits = teacher(batch_inputs).float().reshape(-1, teacher.vocab_size)[batch_masks]
            student_log_probs = F.log_softmax(student_logits, dim=-1)
            teacher_probs = F.softmax(teacher_logits, dim=-1)
            total_kl += float(F.kl_div(student_log_probs, teacher_probs, reduction="sum"))
            total_tokens += int(batch_masks.sum())
    if was_training:
        student.train()
    if total_tokens <= 0:
        raise ValueError("viv_v35_teacher_alignment_empty")
    return {"teacher_kl": total_kl / total_tokens, "tokens": total_tokens}


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def adaptive_teacher_anchor_update(
    state: dict[str, float | int | str | bool],
    *,
    observed_teacher_kl_delta: float,
    observed_validation_nll_delta: float,
) -> dict[str, float | int | str | bool]:
    """Adjust bounded anchor pressure from measured broad-surface drift."""
    alpha = float(state.get("alpha", CONTROLLER_ALPHA))
    kl_ema = alpha * observed_teacher_kl_delta + (1.0 - alpha) * float(state.get("teacher_kl_delta_ema", 0.0))
    validation_ema = alpha * observed_validation_nll_delta + (1.0 - alpha) * float(state.get("validation_nll_delta_ema", 0.0))
    teacher_pressure = _clip(max(0.0, kl_ema) / TARGET_TEACHER_KL_DELTA, 0.0, 1.0)
    validation_pressure = _clip(max(0.0, validation_ema) / TARGET_VALIDATION_NLL_DELTA, 0.0, 1.0)
    anchor_weight = _clip(
        BASE_ANCHOR_WEIGHT * (1.0 + (0.80 * teacher_pressure) + (0.50 * validation_pressure)),
        MIN_ANCHOR_WEIGHT,
        MAX_ANCHOR_WEIGHT,
    )
    lr_scale = _clip(
        1.0 - (0.35 * teacher_pressure) - (0.50 * validation_pressure),
        MIN_LR_SCALE,
        MAX_LR_SCALE,
    )
    return {
        "schema_version": "viv_slm_v35_full_surface_teacher_anchor_controller_v1",
        "alpha": alpha,
        "teacher_kl_delta_ema": kl_ema,
        "validation_nll_delta_ema": validation_ema,
        "teacher_pressure": teacher_pressure,
        "validation_pressure": validation_pressure,
        "anchor_weight": anchor_weight,
        "lr_scale": lr_scale,
    }


def guarded_rollback_decision(
    *,
    metric_guard: bool,
    behavior_guard: bool,
    consecutive_guard_failures: int,
) -> dict[str, bool | int | str]:
    guard_ok = bool(metric_guard and behavior_guard)
    next_failures = 0 if guard_ok else int(consecutive_guard_failures) + 1
    return {
        "guard_ok": guard_ok,
        "rollback": not guard_ok,
        "halt": next_failures >= MAX_CONSECUTIVE_GUARD_FAILURES,
        "consecutive_guard_failures": next_failures,
        "reason": "guard_pass" if guard_ok else "metric_or_behavior_guard_failure",
    }


def train(
    *,
    output_dir: Path = DEFAULT_OUTPUT,
    steps: int = STEP_INCREMENT,
    batch_size: int = 64,
    eval_batch_size: int = 64,
    learning_rate: float = LEARNING_RATE,
    max_grad_norm: float = 1.0,
    seed: int = 42,
    device_name: str = "cuda",
    sample_tokens: int = 160,
    top_k: int = 40,
    authorize: bool = False,
) -> dict[str, Any]:
    if steps <= 0 or steps % STEP_INCREMENT != 0:
        raise ValueError("viv_v35_steps_must_be_positive_multiple_of_250")
    if not math.isclose(learning_rate, LEARNING_RATE, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("viv_v35_learning_rate_is_fixed_for_this_objective")
    if batch_size <= 0 or eval_batch_size <= 0 or max_grad_norm <= 0:
        raise ValueError("viv_v35_optimizer_parameter_invalid")
    if output_dir.exists():
        raise FileExistsError(f"viv_v35_output_exists_refuse_overwrite:{output_dir}")
    authority = _validate_authority(authorize=authorize, steps=steps, learning_rate=learning_rate)
    tokenizer, input_manifest, tensor_dir, source_evidence = _validate_sources()
    train_inputs, train_targets, train_masks = base._load_split(
        tensor_dir,
        "train",
        vocab_size=tokenizer.vocab_size,
        response_only_loss=True,
    )
    validation_inputs, validation_targets, validation_masks = base._load_split(
        tensor_dir,
        "validation",
        vocab_size=tokenizer.vocab_size,
        response_only_loss=True,
    )
    if train_masks is None or validation_masks is None:
        raise ValueError("viv_v35_response_only_masks_required")
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("viv_v35_cuda_requested_but_unavailable")
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)

    model = base._make_model(tokenizer.vocab_size, device=device)
    starting_sample = base._load_warm_start(PARENT_CHECKPOINT, tokenizer=tokenizer, model=model)
    teacher = base._make_model(tokenizer.vocab_size, device=device)
    base._load_warm_start(BEHAVIOR_REFERENCE_CHECKPOINT, tokenizer=tokenizer, model=teacher)
    teacher.eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)

    parent_validation_metrics = base._evaluate(
        model,
        validation_inputs,
        validation_targets,
        device=device,
        batch_size=eval_batch_size,
        loss_masks=validation_masks,
    )
    parent_behavior_alignment = _evaluate_teacher_alignment(
        model,
        teacher,
        validation_inputs,
        validation_masks,
        device=device,
        batch_size=eval_batch_size,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    batch_generator = torch.Generator(device="cpu")
    batch_generator.manual_seed(seed + 350)
    termination_marker = str(input_manifest.get("termination_marker") or "<END>")
    history: list[dict[str, Any]] = []
    best_step = 0
    best_validation_nll = float(parent_validation_metrics["nll"])
    best_validation_accuracy = float(parent_validation_metrics["token_accuracy"])
    best_teacher_kl = float(parent_behavior_alignment["teacher_kl"])
    best_state = base._cpu_state_dict(model)
    latest_validation_delta = 0.0
    latest_teacher_kl_delta = 0.0
    consecutive_guard_failures = 0
    halt_reason: str | None = None
    last_step = 0
    controller_state: dict[str, float | int | str | bool] = {
        "schema_version": "viv_slm_v35_full_surface_teacher_anchor_controller_v1",
        "alpha": CONTROLLER_ALPHA,
        "teacher_kl_delta_ema": 0.0,
        "validation_nll_delta_ema": 0.0,
        "teacher_pressure": 0.0,
        "validation_pressure": 0.0,
        "anchor_weight": BASE_ANCHOR_WEIGHT,
        "lr_scale": 1.0,
    }
    model.train()

    for step in range(1, steps + 1):
        last_step = step
        optimizer.zero_grad(set_to_none=True)
        indices = torch.randint(0, train_inputs.shape[0], (batch_size,), generator=batch_generator)
        batch_inputs = train_inputs[indices].to(device)
        batch_targets = train_targets[indices].to(device)
        batch_masks = train_masks[indices].to(device)
        student_logits = model(batch_inputs)
        with torch.no_grad():
            teacher_logits = teacher(batch_inputs)
        sft_loss = _masked_nll(student_logits, batch_targets, batch_masks)
        anchor_kl = _teacher_anchor_kl(student_logits, teacher_logits, batch_masks)
        anchor_weight = float(controller_state["anchor_weight"])
        total_loss = (SFT_WEIGHT * sft_loss) + (anchor_weight * anchor_kl)
        total_loss.backward()
        effective_learning_rate = learning_rate * float(controller_state["lr_scale"])
        for parameter_group in optimizer.param_groups:
            parameter_group["lr"] = effective_learning_rate
        grad_norm_before = float(torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=max_grad_norm))
        grad_norm_after = math.sqrt(
            sum(float(parameter.grad.detach().float().pow(2).sum()) for parameter in model.parameters() if parameter.grad is not None)
        )
        optimizer.step()

        if step % EVAL_INTERVAL != 0 and step != steps:
            continue
        training_metrics = base._evaluate(
            model,
            train_inputs,
            train_targets,
            device=device,
            batch_size=eval_batch_size,
            loss_masks=train_masks,
        )
        validation_metrics = base._evaluate(
            model,
            validation_inputs,
            validation_targets,
            device=device,
            batch_size=eval_batch_size,
            loss_masks=validation_masks,
        )
        behavior_alignment = _evaluate_teacher_alignment(
            model,
            teacher,
            validation_inputs,
            validation_masks,
            device=device,
            batch_size=eval_batch_size,
        )
        model.train()
        validation_delta = float(validation_metrics["nll"]) - float(parent_validation_metrics["nll"])
        teacher_kl_delta = float(behavior_alignment["teacher_kl"]) - float(parent_behavior_alignment["teacher_kl"])
        latest_validation_delta = validation_delta
        latest_teacher_kl_delta = teacher_kl_delta
        controller_state = adaptive_teacher_anchor_update(
            controller_state,
            observed_teacher_kl_delta=teacher_kl_delta,
            observed_validation_nll_delta=validation_delta,
        )
        metric_guard = (
            float(validation_metrics["nll"]) <= float(parent_validation_metrics["nll"]) + VALIDATION_NLL_TOLERANCE
            and float(validation_metrics["token_accuracy"]) >= float(parent_validation_metrics["token_accuracy"]) - VALIDATION_ACCURACY_TOLERANCE
        )
        behavior_guard = float(behavior_alignment["teacher_kl"]) <= float(parent_behavior_alignment["teacher_kl"]) + TEACHER_KL_TOLERANCE
        metric_improved = (
            float(validation_metrics["nll"]) < best_validation_nll - 1e-9
            or float(validation_metrics["token_accuracy"]) > best_validation_accuracy + 1e-9
        )
        behavior_improved = float(behavior_alignment["teacher_kl"]) < best_teacher_kl - 1e-9
        selected = bool(metric_guard and behavior_guard and (metric_improved or behavior_improved))
        rollback_decision = guarded_rollback_decision(
            metric_guard=metric_guard,
            behavior_guard=behavior_guard,
            consecutive_guard_failures=consecutive_guard_failures,
        )
        consecutive_guard_failures = int(rollback_decision["consecutive_guard_failures"])
        if selected:
            best_validation_nll = float(validation_metrics["nll"])
            best_validation_accuracy = float(validation_metrics["token_accuracy"])
            best_teacher_kl = float(behavior_alignment["teacher_kl"])
            best_step = step
            best_state = base._cpu_state_dict(model)
        if bool(rollback_decision["rollback"]):
            model.load_state_dict(best_state)
            optimizer.state.clear()
            optimizer.zero_grad(set_to_none=True)
        if bool(rollback_decision["halt"]):
            halt_reason = "consecutive_guard_failure_budget_exhausted"
        record = {
            "step": step,
            "training": training_metrics,
            "validation": validation_metrics,
            "parent_validation": parent_validation_metrics,
            "validation_nll_delta_vs_parent": validation_delta,
            "metric_guard": metric_guard,
            "behavior_alignment": behavior_alignment,
            "parent_behavior_alignment": parent_behavior_alignment,
            "teacher_kl_delta_vs_parent": teacher_kl_delta,
            "behavior_guard": behavior_guard,
            "guarded_rollback": bool(rollback_decision["rollback"]),
            "consecutive_guard_failures": consecutive_guard_failures,
            "optimizer_state_reset": bool(rollback_decision["rollback"]),
            "halt_after_record": bool(rollback_decision["halt"]),
            "guard_decision_reason": rollback_decision["reason"],
            "selected_as_best": selected,
            "sft_loss": float(sft_loss.detach()),
            "anchor_kl": float(anchor_kl.detach()),
            "anchor_weight": anchor_weight,
            "effective_learning_rate": effective_learning_rate,
            "controller": dict(controller_state),
            "total_loss": float(total_loss.detach()),
            "grad_norm_before_clip": grad_norm_before,
            "grad_norm_after_clip": grad_norm_after,
            "best_validation_step": best_step,
            "best_validation_nll": best_validation_nll,
            "best_teacher_kl": best_teacher_kl,
        }
        history.append(record)
        print(json.dumps(record, sort_keys=True))
        if halt_reason is not None:
            break

    model.load_state_dict(best_state)
    model.eval()
    generations = [
        {
            "prompt": "Viv:",
            "temperature": temperature,
            "top_k": top_k,
            "generated_token_count": sample_tokens,
            "text": base._sample(
                model,
                tokenizer,
                device=device,
                temperature=temperature,
                top_k=top_k,
                max_new_tokens=sample_tokens,
                seed=seed + 450 + index,
                stop_marker=termination_marker,
            ),
            "stop_marker": termination_marker,
        }
        for index, temperature in enumerate((0.0, 0.25, 0.5, 0.75, 1.0))
    ]
    training_status = "complete" if halt_reason is None else "halted_guard_budget"
    checkpoint = {
        "schema_version": base.CHECKPOINT_SCHEMA,
        "model": base.MODEL_NAME,
        "weights_status": "trained",
        "training_status": training_status,
        "training_steps": last_step,
        "requested_training_steps": steps,
        "halt_reason": halt_reason,
        "selected_state_step": best_step,
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "model_config": base.MODEL_CONFIG,
        "training_config": {
            "batch_size": batch_size,
            "eval_batch_size": eval_batch_size,
            "learning_rate": learning_rate,
            "optimizer": "AdamW",
            "max_grad_norm": max_grad_norm,
            "step_increment": STEP_INCREMENT,
            "evaluation_interval": EVAL_INTERVAL,
            "seed": seed,
            "device": str(device),
            "termination_marker": termination_marker,
            "response_only_loss": True,
            "initialization": "warm_start_v32_full_surface_teacher_anchor_fresh_optimizer",
            "warm_start_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
            "behavior_reference_checkpoint": str(BEHAVIOR_REFERENCE_CHECKPOINT).replace("\\", "/"),
            "objective": {
                "kind": "full_surface_response_only_sft_plus_v28_behavior_teacher_anchor",
                "sft_weight": SFT_WEIGHT,
                "base_anchor_weight": BASE_ANCHOR_WEIGHT,
                "anchor_weight_bounds": [MIN_ANCHOR_WEIGHT, MAX_ANCHOR_WEIGHT],
                "teacher_anchor": "V28 frozen logits on every V31 balanced replay response token",
                "automatic_adjustment": "bounded_teacher_kl_and_validation_drift_controller",
                "controller_schema_version": "viv_slm_v35_full_surface_teacher_anchor_controller_v1",
                "learning_rate_scale_bounds": [MIN_LR_SCALE, MAX_LR_SCALE],
                "metric_guard": {
                    "validation_nll_tolerance": VALIDATION_NLL_TOLERANCE,
                    "validation_accuracy_tolerance": VALIDATION_ACCURACY_TOLERANCE,
                    "teacher_kl_tolerance": TEACHER_KL_TOLERANCE,
                },
            },
        },
        "input_manifest": input_manifest,
        "source_evidence": source_evidence,
        "starting_sample": starting_sample,
        "training_history": history,
        "parent_validation_metrics": parent_validation_metrics,
        "parent_behavior_alignment": parent_behavior_alignment,
        "best_validation_step": best_step,
        "best_validation_nll": best_validation_nll,
        "best_validation_token_accuracy": best_validation_accuracy,
        "best_teacher_kl": best_teacher_kl,
        "best_model_state_dict": best_state,
        "generation_comparison": generations,
        "model_state_dict": base._cpu_state_dict(model),
        "optimizer_state_dict": optimizer.state_dict(),
        "controller_final": dict(controller_state),
        "aifl_integration": "not_used; prior V34 AIFL investigation remains read_only_and_closed",
        "aifl_global_preference_buffer_written": False,
        "aifl_global_train_gate_written": False,
        "master_s_n_mutation": False,
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "aios_live_mutation": False,
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_path = output_dir / "checkpoint.pt"
    torch.save(checkpoint, checkpoint_path)
    run_manifest = {
        "schema_version": base.SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED" if halt_reason is None else "HALTED_GUARD_BUDGET_CLOSED",
        "model": base.MODEL_NAME,
        "weights_status": "trained",
        "training_status": training_status,
        "campaign_id": CAMPAIGN_ID,
        "training_steps": last_step,
        "requested_training_steps": steps,
        "halt_reason": halt_reason,
        "selected_state_step": best_step,
        "step_increment": STEP_INCREMENT,
        "evaluation_interval": EVAL_INTERVAL,
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "input_manifest": source_evidence["input_manifest"],
        "input_manifest_sha256": source_evidence["input_manifest_sha256"],
        "tensor_manifest": source_evidence["tensor_manifest"],
        "tensor_manifest_sha256": source_evidence["tensor_manifest_sha256"],
        "checkpoint": str(checkpoint_path).replace("\\", "/"),
        "checkpoint_sha256": _sha256(checkpoint_path),
        "learning_rate": learning_rate,
        "optimizer": "AdamW",
        "max_grad_norm": max_grad_norm,
        "batch_size": batch_size,
        "eval_batch_size": eval_batch_size,
        "device": str(device),
        "seed": seed,
        "top_k": top_k,
        "sample_tokens": sample_tokens,
        "termination_marker": termination_marker,
        "response_only_loss": True,
        "warm_start_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
        "warm_start_checkpoint_sha256": PARENT_CHECKPOINT_SHA256,
        "behavior_reference_checkpoint": str(BEHAVIOR_REFERENCE_CHECKPOINT).replace("\\", "/"),
        "behavior_reference_checkpoint_sha256": BEHAVIOR_REFERENCE_CHECKPOINT_SHA256,
        "objective": checkpoint["training_config"]["objective"],
        "controller_final": dict(controller_state),
        "parent_validation_metrics": parent_validation_metrics,
        "parent_behavior_alignment": parent_behavior_alignment,
        "best_validation_step": best_step,
        "best_validation_nll": best_validation_nll,
        "best_validation_token_accuracy": best_validation_accuracy,
        "best_teacher_kl": best_teacher_kl,
        "training_authorized": True,
        "run_authorized": True,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "aifl_global_preference_buffer_written": False,
        "aifl_global_train_gate_written": False,
        "master_s_n_mutation": False,
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "aios_live_mutation": False,
        "next_step": "run_matched_v15_semantic_and_cpu_mouth_probes_then_compare_pareto_tradeoffs_before_any_parent_advance",
    }
    _json_write(output_dir / "generation_comparison.json", {"samples": generations})
    _json_write(output_dir / "training_history.json", {"measurements": history})
    _json_write(output_dir / "RUN_MANIFEST.json", run_manifest)
    _json_write(
        output_dir / "AUTHORIZATION.json",
        {
            "schema_version": "viv_slm_v35_training_authorization_v1",
            "campaign_id": CAMPAIGN_ID,
            "authorized_utc": authority["task_updated_utc"],
            "working_parent_layer_id": authority["working_parent_layer_id"],
            "behavior_reference_layer_id": authority["behavior_reference_layer_id"],
            "input_manifest_sha256": source_evidence["input_manifest_sha256"],
            "tensor_manifest_sha256": source_evidence["tensor_manifest_sha256"],
            "parent_checkpoint": authority["parent_checkpoint"],
            "parent_checkpoint_sha256": authority["parent_checkpoint_sha256"],
            "behavior_reference_checkpoint": authority["behavior_reference_checkpoint"],
            "behavior_reference_checkpoint_sha256": authority["behavior_reference_checkpoint_sha256"],
            "steps": steps,
            "step_increment": STEP_INCREMENT,
            "evaluation_interval": EVAL_INTERVAL,
            "learning_rate": learning_rate,
            "objective": checkpoint["training_config"]["objective"],
            "training_authorized": True,
            "run_authorized": True,
            "promotion_authorized": False,
            "deployment_changed": False,
            "live_model_changed": False,
        },
    )
    (output_dir / "RUN_REPORT.md").write_text(
        "# Viv-SLM V35 full-surface teacher-anchor run\n\n"
        f"- Completed optimizer steps: {last_step}\n"
        f"- Requested optimizer steps: {steps}\n"
        f"- Halt reason: {halt_reason or 'none'}\n"
        f"- Selected state step: {best_step}\n"
        f"- Best validation NLL: {best_validation_nll}\n"
        f"- Best validation token accuracy: {best_validation_accuracy}\n"
        f"- Best V28 teacher KL: {best_teacher_kl}\n"
        "- Broad objective: V31 balanced response-only SFT plus frozen V28 behavior anchor\n"
        "- Automatic correction: bounded teacher-divergence/validation controller with rollback\n"
        "- AIFL/global preference writes: false/false; prior AIFL investigation not repeated\n"
        "- World knowledge included: false\n"
        "- AIOS live mutation: false\n"
        "- Promotion/deployment: closed\n",
        encoding="utf-8",
        newline="\n",
    )
    run_manifest["governance"] = authority
    _json_write(output_dir / "RUN_MANIFEST.json", run_manifest)
    return run_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--steps", type=int, default=STEP_INCREMENT)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--eval-batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=LEARNING_RATE)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--sample-tokens", type=int, default=160)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--authorize", action="store_true")
    args = parser.parse_args(argv)
    result = train(
        output_dir=args.output_dir,
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
                "status": "VIV_SLM_V35_FULL_SURFACE_TEACHER_ANCHOR_TRAINING_COMPLETE",
                "campaign_id": CAMPAIGN_ID,
                "checkpoint": result["checkpoint"],
                "training_steps": result["training_steps"],
                "training_status": result["training_status"],
                "best_validation_nll": result["best_validation_nll"],
                "best_validation_token_accuracy": result["best_validation_token_accuracy"],
                "best_teacher_kl": result["best_teacher_kl"],
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
