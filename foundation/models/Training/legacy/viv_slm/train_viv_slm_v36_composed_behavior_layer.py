#!/usr/bin/env python3
"""Run one bounded V36 composed behavior-layer Viv-SLM canary.

V36 composes the preserved V34 specialized behavior delta (V34 - V32) on top
of the accepted V35 working parent.  It evaluates a small, fixed descending
scale ladder before training and chooses the largest composition that stays
inside V35's metric and V28 behavior guards.  The chosen state then receives
one fresh full-surface V31 SFT plus V28 teacher-anchor increment with the same
bounded controller and rollback budget.  Every result is a new immutable
layer; no prior checkpoint is modified.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
SCRIPT_ROOT = FOUNDATION / "scripts"
MODEL_ROOT = VIV_ROOT / "models" / "uml_bigram_part3"
for path in (FOUNDATION, SCRIPT_ROOT, VIV_ROOT, MODEL_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import train_viv_slm_identity_v1 as base  # noqa: E402
import train_viv_slm_v35_full_surface_teacher_anchor as v35  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v31_balanced_base" / "inputs"
PARENT_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v35_full_surface_teacher_anchor" / "runs" / "full_surface_teacher_anchor_steps_0250" / "checkpoint.pt"
SPECIALIZED_LAYER_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v34_conflict_aware_identity" / "runs" / "conflict_aware_identity_steps_0250" / "checkpoint.pt"
SPECIALIZED_BASE_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v32_balanced_low_lr" / "runs" / "balanced_low_lr_steps_0250" / "checkpoint.pt"
BEHAVIOR_REFERENCE_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v28_canonical_disambiguation" / "runs" / "canonical_disambiguation_steps_0250" / "checkpoint.pt"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v36_composed_behavior_layer" / "runs" / "composed_behavior_layer_steps_0250"
CURRENT_TASK = FOUNDATION / "artifacts" / "auto" / "agentic" / "CURRENT_TASK.json"

INPUT_SCHEMA_VERSION = "viv_slm_v31_balanced_base_inputs_v1"
INPUT_MANIFEST_SHA256 = "18446924D85E554A1D6452F011F88798CC4948D8D66CC021165C0B25F9953D72"
VOCAB_FILE_SHA256 = "00982C5992060D4D55E4843D0726A9823CCB71C46E04FC9E9DFFBCDB1D3F8179"
TENSOR_MANIFEST_SHA256 = "23C6B5B8C4C5B9341847285B2FF5C200800B40AC7A1D9655A82BCBBBD5A24B6E"
PARENT_CHECKPOINT_SHA256 = "E03E3497ACEF4E7D8CE5CB539534F0822B342B17BD5E89980E16FD9B94CA86D1"
SPECIALIZED_LAYER_CHECKPOINT_SHA256 = "22D31C238C384E69DB4D662AEC6F19CB518ED02D949C74447729900C9BB988EE"
SPECIALIZED_BASE_CHECKPOINT_SHA256 = "EC7065B19C6630B7CF3DD64AE78FD92371A02A4A4E7465EF3206AB6CE30EE2F9"
BEHAVIOR_REFERENCE_CHECKPOINT_SHA256 = "99D536EE2E0AB804B70B54B4C81C617468564F825EAE82E2F6296964796C1BF0"
STEP_INCREMENT = 250
EVAL_INTERVAL = 50
LEARNING_RATE = 0.0001
COMPOSITION_SCALES = (1.0, 0.75, 0.5, 0.25, 0.1)
VALIDATION_NLL_TOLERANCE = v35.VALIDATION_NLL_TOLERANCE
VALIDATION_ACCURACY_TOLERANCE = v35.VALIDATION_ACCURACY_TOLERANCE
TEACHER_KL_TOLERANCE = v35.TEACHER_KL_TOLERANCE
CAMPAIGN_ID = "viv_slm_identity_personality_v36_composed_behavior_layer_0250"


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"viv_v36_expected_json_object:{path}")
    return value


def _validate_authority(*, authorize: bool, steps: int, learning_rate: float) -> dict[str, Any]:
    if not authorize:
        raise PermissionError("v36_composed_behavior_layer_requires_explicit_authorize_flag")
    task = _read_json(CURRENT_TASK)
    record = task.get("v36_composed_behavior_layer_training")
    if not isinstance(record, dict):
        raise PermissionError("v36_composed_behavior_layer_task_authorization_record_missing")
    if record.get("training_authorized") is not True or record.get("run_authorized") is not True:
        raise PermissionError("v36_composed_behavior_layer_task_authorization_closed")
    if record.get("promotion_authorized") is not False or record.get("deployment_changed") is not False:
        raise PermissionError("v36_composed_behavior_layer_promotion_or_deployment_state_invalid")
    if record.get("working_parent_layer_id") != "viv_slm_identity_personality_v35_full_surface_teacher_anchor_0250_20260804T211956Z":
        raise PermissionError("v36_composed_behavior_layer_working_parent_invalid")
    scope = record.get("scope")
    if not isinstance(scope, dict) or int(scope.get("steps", -1)) != steps:
        raise PermissionError("v36_composed_behavior_layer_scope_steps_invalid")
    if not math.isclose(float(scope.get("learning_rate", -1.0)), learning_rate, rel_tol=0.0, abs_tol=1e-12):
        raise PermissionError("v36_composed_behavior_layer_scope_learning_rate_invalid")
    expected = {
        "parent_checkpoint_sha256": PARENT_CHECKPOINT_SHA256,
        "specialized_layer_checkpoint_sha256": SPECIALIZED_LAYER_CHECKPOINT_SHA256,
        "specialized_base_checkpoint_sha256": SPECIALIZED_BASE_CHECKPOINT_SHA256,
        "behavior_reference_checkpoint_sha256": BEHAVIOR_REFERENCE_CHECKPOINT_SHA256,
    }
    for key, value in expected.items():
        if str(record.get(key) or "").casefold() != value.casefold():
            raise PermissionError(f"v36_composed_behavior_layer_{key}_invalid")
    return {
        "campaign_id": CAMPAIGN_ID,
        "task_updated_utc": str(task.get("updated_utc") or ""),
        "working_parent_layer_id": record["working_parent_layer_id"],
        "behavior_reference_layer_id": record.get("behavior_reference_layer_id"),
        "parent_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
        "parent_checkpoint_sha256": PARENT_CHECKPOINT_SHA256,
        "specialized_layer_checkpoint": str(SPECIALIZED_LAYER_CHECKPOINT).replace("\\", "/"),
        "specialized_layer_checkpoint_sha256": SPECIALIZED_LAYER_CHECKPOINT_SHA256,
        "specialized_base_checkpoint": str(SPECIALIZED_BASE_CHECKPOINT).replace("\\", "/"),
        "specialized_base_checkpoint_sha256": SPECIALIZED_BASE_CHECKPOINT_SHA256,
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
    sources = (input_manifest_path, vocab_path, tensor_manifest_path, PARENT_CHECKPOINT, SPECIALIZED_LAYER_CHECKPOINT, SPECIALIZED_BASE_CHECKPOINT, BEHAVIOR_REFERENCE_CHECKPOINT)
    for path in sources:
        if not path.is_file():
            raise FileNotFoundError(f"viv_v36_source_missing:{path}")
    manifest = _read_json(input_manifest_path)
    if manifest.get("schema_version") != INPUT_SCHEMA_VERSION or manifest.get("world_knowledge_included") is not False or manifest.get("response_only_loss") is not True:
        raise ValueError("viv_v36_input_policy_mismatch")
    if manifest.get("training_authorized") is not False or manifest.get("run_authorized") is not False:
        raise ValueError("viv_v36_input_authority_flags_changed")
    expected = {
        input_manifest_path: INPUT_MANIFEST_SHA256,
        vocab_path: VOCAB_FILE_SHA256,
        tensor_manifest_path: TENSOR_MANIFEST_SHA256,
        PARENT_CHECKPOINT: PARENT_CHECKPOINT_SHA256,
        SPECIALIZED_LAYER_CHECKPOINT: SPECIALIZED_LAYER_CHECKPOINT_SHA256,
        SPECIALIZED_BASE_CHECKPOINT: SPECIALIZED_BASE_CHECKPOINT_SHA256,
        BEHAVIOR_REFERENCE_CHECKPOINT: BEHAVIOR_REFERENCE_CHECKPOINT_SHA256,
    }
    for path, expected_hash in expected.items():
        actual = _sha256(path)
        if actual.casefold() != expected_hash.casefold():
            raise ValueError(f"viv_v36_source_hash_mismatch:{path}:{actual}")
    tokenizer, validated_manifest, tensor_dir = base._validate_input(INPUT_ROOT)
    if validated_manifest != manifest:
        raise ValueError("viv_v36_input_manifest_read_mismatch")
    return tokenizer, manifest, tensor_dir, {
        "input_manifest": str(input_manifest_path).replace("\\", "/"),
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "vocab_file_sha256": VOCAB_FILE_SHA256,
        "tensor_manifest": str(tensor_manifest_path).replace("\\", "/"),
        "tensor_manifest_sha256": TENSOR_MANIFEST_SHA256,
        "parent_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
        "parent_checkpoint_sha256": PARENT_CHECKPOINT_SHA256,
        "specialized_layer_checkpoint": str(SPECIALIZED_LAYER_CHECKPOINT).replace("\\", "/"),
        "specialized_layer_checkpoint_sha256": SPECIALIZED_LAYER_CHECKPOINT_SHA256,
        "specialized_base_checkpoint": str(SPECIALIZED_BASE_CHECKPOINT).replace("\\", "/"),
        "specialized_base_checkpoint_sha256": SPECIALIZED_BASE_CHECKPOINT_SHA256,
        "behavior_reference_checkpoint": str(BEHAVIOR_REFERENCE_CHECKPOINT).replace("\\", "/"),
        "behavior_reference_checkpoint_sha256": BEHAVIOR_REFERENCE_CHECKPOINT_SHA256,
        "schema_version": INPUT_SCHEMA_VERSION,
        "world_knowledge_included": False,
    }


def _state_from_checkpoint(path: Path) -> dict[str, torch.Tensor]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != base.CHECKPOINT_SCHEMA:
        raise ValueError(f"viv_v36_checkpoint_schema_mismatch:{path}")
    state = checkpoint.get("best_model_state_dict") or checkpoint.get("model_state_dict")
    if not isinstance(state, Mapping):
        raise ValueError(f"viv_v36_checkpoint_state_missing:{path}")
    return {str(key): value.detach().cpu().clone() for key, value in state.items()}


def compose_state(parent: Mapping[str, torch.Tensor], specialized: Mapping[str, torch.Tensor], specialized_base: Mapping[str, torch.Tensor], scale: float) -> dict[str, torch.Tensor]:
    if scale < 0.0 or scale > 1.0:
        raise ValueError("viv_v36_composition_scale_out_of_bounds")
    if set(parent) != set(specialized) or set(parent) != set(specialized_base):
        raise ValueError("viv_v36_composition_state_keys_mismatch")
    composed: dict[str, torch.Tensor] = {}
    for key, parent_value in parent.items():
        if not isinstance(parent_value, torch.Tensor):
            raise ValueError("viv_v36_parent_state_value_invalid")
        if torch.is_floating_point(parent_value):
            composed[key] = parent_value + (float(scale) * (specialized[key].float() - specialized_base[key].float()))
        else:
            composed[key] = parent_value.clone()
    return composed


def _evaluate_state(model: torch.nn.Module, teacher: torch.nn.Module, state: Mapping[str, torch.Tensor], inputs: torch.Tensor, targets: torch.Tensor, masks: torch.Tensor, *, device: torch.device, batch_size: int) -> tuple[dict[str, Any], dict[str, Any]]:
    model.load_state_dict(state, strict=True)
    metrics = base._evaluate(model, inputs, targets, device=device, batch_size=batch_size, loss_masks=masks)
    alignment = v35._evaluate_teacher_alignment(model, teacher, inputs, masks, device=device, batch_size=batch_size)
    return metrics, alignment


def _select_composition(model: torch.nn.Module, teacher: torch.nn.Module, parent_state: Mapping[str, torch.Tensor], specialized_state: Mapping[str, torch.Tensor], base_state: Mapping[str, torch.Tensor], inputs: torch.Tensor, targets: torch.Tensor, masks: torch.Tensor, *, device: torch.device, batch_size: int) -> tuple[float, dict[str, torch.Tensor], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    parent_metrics, parent_alignment = _evaluate_state(model, teacher, parent_state, inputs, targets, masks, device=device, batch_size=batch_size)
    trials: list[dict[str, Any]] = []
    eligible: list[tuple[float, dict[str, torch.Tensor], dict[str, Any], dict[str, Any]]] = []
    for scale in (0.0, *COMPOSITION_SCALES):
        state = parent_state if scale == 0.0 else compose_state(parent_state, specialized_state, base_state, scale)
        metrics, alignment = _evaluate_state(model, teacher, state, inputs, targets, masks, device=device, batch_size=batch_size)
        metric_guard = float(metrics["nll"]) <= float(parent_metrics["nll"]) + VALIDATION_NLL_TOLERANCE and float(metrics["token_accuracy"]) >= float(parent_metrics["token_accuracy"]) - VALIDATION_ACCURACY_TOLERANCE
        behavior_guard = float(alignment["teacher_kl"]) <= float(parent_alignment["teacher_kl"]) + TEACHER_KL_TOLERANCE
        improved = float(metrics["nll"]) < float(parent_metrics["nll"]) - 1e-9 or float(metrics["token_accuracy"]) > float(parent_metrics["token_accuracy"]) + 1e-9 or float(alignment["teacher_kl"]) < float(parent_alignment["teacher_kl"]) - 1e-9
        trial = {"scale": scale, "validation": metrics, "behavior_alignment": alignment, "metric_guard": metric_guard, "behavior_guard": behavior_guard, "improved_vs_v35": improved, "selected": False}
        trials.append(trial)
        if scale > 0.0 and metric_guard and behavior_guard and improved:
            eligible.append((scale, state, metrics, alignment))
    if eligible:
        scale, selected_state, metrics, alignment = sorted(eligible, key=lambda item: item[0], reverse=True)[0]
        for trial in trials:
            if float(trial["scale"]) == scale:
                trial["selected"] = True
        return scale, selected_state, metrics, alignment, trials
    return 0.0, dict(parent_state), parent_metrics, parent_alignment, trials


def train(*, output_dir: Path = DEFAULT_OUTPUT, steps: int = STEP_INCREMENT, batch_size: int = 64, eval_batch_size: int = 64, learning_rate: float = LEARNING_RATE, max_grad_norm: float = 1.0, seed: int = 42, device_name: str = "cuda", sample_tokens: int = 160, top_k: int = 40, authorize: bool = False) -> dict[str, Any]:
    if steps <= 0 or steps % STEP_INCREMENT != 0:
        raise ValueError("viv_v36_steps_must_be_positive_multiple_of_250")
    if not math.isclose(learning_rate, LEARNING_RATE, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("viv_v36_learning_rate_is_fixed_for_this_objective")
    if output_dir.exists():
        raise FileExistsError(f"viv_v36_output_exists_refuse_overwrite:{output_dir}")
    authority = _validate_authority(authorize=authorize, steps=steps, learning_rate=learning_rate)
    tokenizer, input_manifest, tensor_dir, source_evidence = _validate_sources()
    train_inputs, train_targets, train_masks = base._load_split(tensor_dir, "train", vocab_size=tokenizer.vocab_size, response_only_loss=True)
    validation_inputs, validation_targets, validation_masks = base._load_split(tensor_dir, "validation", vocab_size=tokenizer.vocab_size, response_only_loss=True)
    if train_masks is None or validation_masks is None:
        raise ValueError("viv_v36_response_only_masks_required")
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("viv_v36_cuda_requested_but_unavailable")
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
    model = base._make_model(tokenizer.vocab_size, device=device)
    starting_sample = base._load_warm_start(PARENT_CHECKPOINT, tokenizer=tokenizer, model=model)
    parent_state = base._cpu_state_dict(model)
    specialized_state = _state_from_checkpoint(SPECIALIZED_LAYER_CHECKPOINT)
    specialized_base_state = _state_from_checkpoint(SPECIALIZED_BASE_CHECKPOINT)
    teacher = base._make_model(tokenizer.vocab_size, device=device)
    base._load_warm_start(BEHAVIOR_REFERENCE_CHECKPOINT, tokenizer=tokenizer, model=teacher)
    teacher.eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)
    selected_scale, selected_state, parent_validation_metrics, parent_behavior_alignment, composition_trials = _select_composition(
        model, teacher, parent_state, specialized_state, specialized_base_state, validation_inputs, validation_targets, validation_masks, device=device, batch_size=eval_batch_size
    )
    model.load_state_dict(selected_state, strict=True)
    selected_initial_metrics = base._evaluate(model, validation_inputs, validation_targets, device=device, batch_size=eval_batch_size, loss_masks=validation_masks)
    selected_initial_alignment = v35._evaluate_teacher_alignment(model, teacher, validation_inputs, validation_masks, device=device, batch_size=eval_batch_size)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    batch_generator = torch.Generator(device="cpu")
    batch_generator.manual_seed(seed + 360)
    termination_marker = str(input_manifest.get("termination_marker") or "<END>")
    history: list[dict[str, Any]] = []
    best_step = 0
    best_validation_nll = float(selected_initial_metrics["nll"])
    best_validation_accuracy = float(selected_initial_metrics["token_accuracy"])
    best_teacher_kl = float(selected_initial_alignment["teacher_kl"])
    best_state = {key: value.detach().cpu().clone() for key, value in selected_state.items()}
    consecutive_guard_failures = 0
    halt_reason: str | None = None
    last_step = 0
    controller_state: dict[str, float | int | str | bool] = {"schema_version": "viv_slm_v35_full_surface_teacher_anchor_controller_v1", "alpha": v35.CONTROLLER_ALPHA, "teacher_kl_delta_ema": 0.0, "validation_nll_delta_ema": 0.0, "teacher_pressure": 0.0, "validation_pressure": 0.0, "anchor_weight": v35.BASE_ANCHOR_WEIGHT, "lr_scale": 1.0}
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
        sft_loss = v35._masked_nll(student_logits, batch_targets, batch_masks)
        anchor_kl = v35._teacher_anchor_kl(student_logits, teacher_logits, batch_masks)
        anchor_weight = float(controller_state["anchor_weight"])
        total_loss = sft_loss + (anchor_weight * anchor_kl)
        total_loss.backward()
        effective_learning_rate = learning_rate * float(controller_state["lr_scale"])
        for group in optimizer.param_groups:
            group["lr"] = effective_learning_rate
        grad_norm_before = float(torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=max_grad_norm))
        grad_norm_after = math.sqrt(sum(float(parameter.grad.detach().float().pow(2).sum()) for parameter in model.parameters() if parameter.grad is not None))
        optimizer.step()
        if step % EVAL_INTERVAL != 0 and step != steps:
            continue
        training_metrics = base._evaluate(model, train_inputs, train_targets, device=device, batch_size=eval_batch_size, loss_masks=train_masks)
        validation_metrics = base._evaluate(model, validation_inputs, validation_targets, device=device, batch_size=eval_batch_size, loss_masks=validation_masks)
        behavior_alignment = v35._evaluate_teacher_alignment(model, teacher, validation_inputs, validation_masks, device=device, batch_size=eval_batch_size)
        model.train()
        validation_delta = float(validation_metrics["nll"]) - float(parent_validation_metrics["nll"])
        teacher_kl_delta = float(behavior_alignment["teacher_kl"]) - float(parent_behavior_alignment["teacher_kl"])
        controller_state = v35.adaptive_teacher_anchor_update(controller_state, observed_teacher_kl_delta=teacher_kl_delta, observed_validation_nll_delta=validation_delta)
        metric_guard = float(validation_metrics["nll"]) <= float(parent_validation_metrics["nll"]) + VALIDATION_NLL_TOLERANCE and float(validation_metrics["token_accuracy"]) >= float(parent_validation_metrics["token_accuracy"]) - VALIDATION_ACCURACY_TOLERANCE
        behavior_guard = float(behavior_alignment["teacher_kl"]) <= float(parent_behavior_alignment["teacher_kl"]) + TEACHER_KL_TOLERANCE
        improved = float(validation_metrics["nll"]) < best_validation_nll - 1e-9 or float(validation_metrics["token_accuracy"]) > best_validation_accuracy + 1e-9 or float(behavior_alignment["teacher_kl"]) < best_teacher_kl - 1e-9
        selected = bool(metric_guard and behavior_guard and improved)
        decision = v35.guarded_rollback_decision(metric_guard=metric_guard, behavior_guard=behavior_guard, consecutive_guard_failures=consecutive_guard_failures)
        consecutive_guard_failures = int(decision["consecutive_guard_failures"])
        if selected:
            best_validation_nll = float(validation_metrics["nll"])
            best_validation_accuracy = float(validation_metrics["token_accuracy"])
            best_teacher_kl = float(behavior_alignment["teacher_kl"])
            best_step = step
            best_state = base._cpu_state_dict(model)
        if bool(decision["rollback"]):
            model.load_state_dict(best_state, strict=True)
            optimizer.state.clear()
            optimizer.zero_grad(set_to_none=True)
        if bool(decision["halt"]):
            halt_reason = "consecutive_guard_failure_budget_exhausted"
        record = {"step": step, "training": training_metrics, "validation": validation_metrics, "parent_validation": parent_validation_metrics, "validation_nll_delta_vs_parent": validation_delta, "metric_guard": metric_guard, "behavior_alignment": behavior_alignment, "parent_behavior_alignment": parent_behavior_alignment, "teacher_kl_delta_vs_parent": teacher_kl_delta, "behavior_guard": behavior_guard, "guarded_rollback": bool(decision["rollback"]), "consecutive_guard_failures": consecutive_guard_failures, "optimizer_state_reset": bool(decision["rollback"]), "halt_after_record": bool(decision["halt"]), "guard_decision_reason": decision["reason"], "selected_as_best": selected, "sft_loss": float(sft_loss.detach()), "anchor_kl": float(anchor_kl.detach()), "anchor_weight": anchor_weight, "effective_learning_rate": effective_learning_rate, "controller": dict(controller_state), "total_loss": float(total_loss.detach()), "grad_norm_before_clip": grad_norm_before, "grad_norm_after_clip": grad_norm_after, "best_validation_step": best_step, "best_validation_nll": best_validation_nll, "best_teacher_kl": best_teacher_kl}
        history.append(record)
        print(json.dumps(record, sort_keys=True))
        if halt_reason is not None:
            break
    model.load_state_dict(best_state, strict=True)
    model.eval()
    generations = [{"prompt": "Viv:", "temperature": temperature, "top_k": top_k, "generated_token_count": sample_tokens, "text": base._sample(model, tokenizer, device=device, temperature=temperature, top_k=top_k, max_new_tokens=sample_tokens, seed=seed + 460 + index, stop_marker=termination_marker), "stop_marker": termination_marker} for index, temperature in enumerate((0.0, 0.25, 0.5, 0.75, 1.0))]
    training_status = "complete" if halt_reason is None else "halted_guard_budget"
    objective = {"kind": "v35_full_surface_teacher_anchor_plus_v34_minus_v32_composed_behavior_layer", "composition_scales": list(COMPOSITION_SCALES), "selected_composition_scale": selected_scale, "specialized_layer": "V34", "specialized_base": "V32", "base_anchor_weight": v35.BASE_ANCHOR_WEIGHT, "automatic_adjustment": "largest_guarded_composition_then_bounded_teacher_kl_and_validation_controller", "metric_guard": {"validation_nll_tolerance": VALIDATION_NLL_TOLERANCE, "validation_accuracy_tolerance": VALIDATION_ACCURACY_TOLERANCE, "teacher_kl_tolerance": TEACHER_KL_TOLERANCE}}
    checkpoint = {"schema_version": base.CHECKPOINT_SCHEMA, "model": base.MODEL_NAME, "weights_status": "trained", "training_status": training_status, "training_steps": last_step, "requested_training_steps": steps, "halt_reason": halt_reason, "selected_state_step": best_step, "vocab_size": tokenizer.vocab_size, "vocab_sha256": tokenizer.vocab_sha256, "model_config": base.MODEL_CONFIG, "training_config": {"batch_size": batch_size, "eval_batch_size": eval_batch_size, "learning_rate": learning_rate, "optimizer": "AdamW", "max_grad_norm": max_grad_norm, "step_increment": STEP_INCREMENT, "evaluation_interval": EVAL_INTERVAL, "seed": seed, "device": str(device), "termination_marker": termination_marker, "response_only_loss": True, "initialization": "warm_start_v35_with_guarded_v34_minus_v32_composition", "warm_start_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"), "specialized_layer_checkpoint": str(SPECIALIZED_LAYER_CHECKPOINT).replace("\\", "/"), "specialized_base_checkpoint": str(SPECIALIZED_BASE_CHECKPOINT).replace("\\", "/"), "behavior_reference_checkpoint": str(BEHAVIOR_REFERENCE_CHECKPOINT).replace("\\", "/"), "objective": objective}, "input_manifest": input_manifest, "source_evidence": source_evidence, "starting_sample": starting_sample, "composition_trials": composition_trials, "selected_initial_metrics": selected_initial_metrics, "selected_initial_behavior_alignment": selected_initial_alignment, "training_history": history, "parent_validation_metrics": parent_validation_metrics, "parent_behavior_alignment": parent_behavior_alignment, "best_validation_step": best_step, "best_validation_nll": best_validation_nll, "best_validation_token_accuracy": best_validation_accuracy, "best_teacher_kl": best_teacher_kl, "best_model_state_dict": best_state, "generation_comparison": generations, "model_state_dict": base._cpu_state_dict(model), "optimizer_state_dict": optimizer.state_dict(), "controller_final": dict(controller_state), "knowledge_policy": "external_cpu_retrieval_only", "world_knowledge_included": False, "aifl_integration": "not_used; prior AIFL investigation remains read_only_and_closed", "aifl_global_preference_buffer_written": False, "aifl_global_train_gate_written": False, "master_s_n_mutation": False, "aios_live_mutation": False}
    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_path = output_dir / "checkpoint.pt"
    torch.save(checkpoint, checkpoint_path)
    run_manifest = {"schema_version": base.SCHEMA_VERSION, "status": "COMPLETE_TRAINING_CLOSED" if halt_reason is None else "HALTED_GUARD_BUDGET_CLOSED", "model": base.MODEL_NAME, "weights_status": "trained", "training_status": training_status, "campaign_id": CAMPAIGN_ID, "training_steps": last_step, "requested_training_steps": steps, "halt_reason": halt_reason, "selected_state_step": best_step, "step_increment": STEP_INCREMENT, "evaluation_interval": EVAL_INTERVAL, "vocab_size": tokenizer.vocab_size, "vocab_sha256": tokenizer.vocab_sha256, "input_manifest": source_evidence["input_manifest"], "input_manifest_sha256": source_evidence["input_manifest_sha256"], "tensor_manifest": source_evidence["tensor_manifest"], "tensor_manifest_sha256": source_evidence["tensor_manifest_sha256"], "checkpoint": str(checkpoint_path).replace("\\", "/"), "checkpoint_sha256": _sha256(checkpoint_path), "learning_rate": learning_rate, "optimizer": "AdamW", "max_grad_norm": max_grad_norm, "batch_size": batch_size, "eval_batch_size": eval_batch_size, "device": str(device), "seed": seed, "top_k": top_k, "sample_tokens": sample_tokens, "termination_marker": termination_marker, "response_only_loss": True, "warm_start_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"), "warm_start_checkpoint_sha256": PARENT_CHECKPOINT_SHA256, "specialized_layer_checkpoint": str(SPECIALIZED_LAYER_CHECKPOINT).replace("\\", "/"), "specialized_layer_checkpoint_sha256": SPECIALIZED_LAYER_CHECKPOINT_SHA256, "specialized_base_checkpoint": str(SPECIALIZED_BASE_CHECKPOINT).replace("\\", "/"), "specialized_base_checkpoint_sha256": SPECIALIZED_BASE_CHECKPOINT_SHA256, "behavior_reference_checkpoint": str(BEHAVIOR_REFERENCE_CHECKPOINT).replace("\\", "/"), "behavior_reference_checkpoint_sha256": BEHAVIOR_REFERENCE_CHECKPOINT_SHA256, "objective": objective, "composition_trials": composition_trials, "selected_composition_scale": selected_scale, "selected_initial_metrics": selected_initial_metrics, "selected_initial_behavior_alignment": selected_initial_alignment, "controller_final": dict(controller_state), "parent_validation_metrics": parent_validation_metrics, "parent_behavior_alignment": parent_behavior_alignment, "best_validation_step": best_step, "best_validation_nll": best_validation_nll, "best_validation_token_accuracy": best_validation_accuracy, "best_validation_accuracy": best_validation_accuracy, "best_teacher_kl": best_teacher_kl, "training_authorized": True, "run_authorized": True, "promotion_authorized": False, "deployment_changed": False, "live_model_changed": False, "aifl_global_preference_buffer_written": False, "aifl_global_train_gate_written": False, "master_s_n_mutation": False, "knowledge_policy": "external_cpu_retrieval_only", "world_knowledge_included": False, "aios_live_mutation": False, "next_step": "run_matched_v15_semantic_and_cpu_mouth_probes_then compare_against_v35_and_v28_before_parent_advance"}
    _json_write(output_dir / "generation_comparison.json", {"samples": generations})
    _json_write(output_dir / "training_history.json", {"measurements": history})
    _json_write(output_dir / "RUN_MANIFEST.json", run_manifest)
    _json_write(output_dir / "AUTHORIZATION.json", {"schema_version": "viv_slm_v36_training_authorization_v1", "campaign_id": CAMPAIGN_ID, "authorized_utc": authority["task_updated_utc"], **authority, "steps": steps, "step_increment": STEP_INCREMENT, "evaluation_interval": EVAL_INTERVAL, "learning_rate": learning_rate, "objective": objective})
    (output_dir / "RUN_REPORT.md").write_text("# Viv-SLM V36 composed behavior-layer run\n\n" + f"- Completed optimizer steps: {last_step}\n- Requested optimizer steps: {steps}\n- Selected composition scale: {selected_scale}\n- Halt reason: {halt_reason or 'none'}\n- Selected state step: {best_step}\n- Best validation NLL: {best_validation_nll}\n- Best validation token accuracy: {best_validation_accuracy}\n- Best V28 teacher KL: {best_teacher_kl}\n- Composition: guarded V34 minus V32 delta on V35\n- Promotion/deployment/live mutation: closed/false/false\n", encoding="utf-8", newline="\n")
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
    result = train(output_dir=args.output_dir, steps=args.steps, batch_size=args.batch_size, eval_batch_size=args.eval_batch_size, learning_rate=args.learning_rate, max_grad_norm=args.max_grad_norm, seed=args.seed, device_name=args.device, sample_tokens=args.sample_tokens, top_k=args.top_k, authorize=args.authorize)
    print(json.dumps({"status": "VIV_SLM_V36_COMPOSED_BEHAVIOR_LAYER_TRAINING_COMPLETE", "campaign_id": CAMPAIGN_ID, "checkpoint": result["checkpoint"], "training_steps": result["training_steps"], "training_status": result["training_status"], "selected_composition_scale": result["selected_composition_scale"], "best_validation_nll": result["best_validation_nll"], "best_validation_token_accuracy": result["best_validation_token_accuracy"], "best_teacher_kl": result["best_teacher_kl"], "training_authorized": result["training_authorized"], "run_authorized": result["run_authorized"], "promotion_authorized": result["promotion_authorized"], "deployment_changed": result["deployment_changed"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
