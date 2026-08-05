#!/usr/bin/env python3
"""Run a declarative, bounded Viv-SLM layer campaign.

The V34-V36 trainers remain frozen executable specifications.  This engine is
the reusable path for future campaigns: a JSON contract supplies lineage,
delta sources, scale ladder, guards, teacher, probes, and authority scope;
this engine owns read-only compatibility checks, composition, one 250-step
consolidation, rollback, and immutable run receipts.  It never promotes,
deploys, mutates live runtime state, writes global AIFL state, or admits
knowledge.
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
from torch.nn import functional as F

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
SCRIPT_ROOT = FOUNDATION / "scripts"
MODEL_ROOT = VIV_ROOT / "models" / "uml_bigram_part3"
for path in (FOUNDATION, SCRIPT_ROOT, VIV_ROOT, MODEL_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import train_viv_slm_identity_v1 as base  # noqa: E402
import run_viv_slm_layered_training_supervisor as supervisor  # noqa: E402
from lib.viv_slm_layer_governor import (  # noqa: E402
    adaptive_controller_update,
    LayerCampaignSpec,
    evaluate_scale_ladder,
    guarded_rollback_decision,
    require_one_increment,
    seed_controller_actuation_state,
    validate_authority_record,
    validate_layer_campaign_spec,
)


DEFAULT_TASK = FOUNDATION / "artifacts" / "auto" / "agentic" / "CURRENT_TASK.json"
DEFAULT_LEDGER = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_checkpoint_layers.json"
DEFAULT_CONTRACT = FOUNDATION / "artifacts" / "auto" / "agentic" / "layer_campaign_contracts" / "V36_COMPOSED_BEHAVIOR_LAYER.json"
DEFAULT_KNOB_REGISTRY = FOUNDATION / "models" / "Training" / "current" / "TRAINING_KNOBS.json"
ENGINE_SCHEMA_VERSION = "viv_slm_layer_campaign_engine_v1"
DEFAULT_DEVICE = "cuda"


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"viv_slm_layer_campaign_expected_json_object:{path}")
    return value


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _resolve_path(value: str | Path) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else VIV_ROOT / path


def _config(spec: LayerCampaignSpec, key: str, default: Any) -> Any:
    return spec.training_config.get(key, default)


def _load_knob_registry(spec: LayerCampaignSpec) -> dict[str, Any]:
    """Load and hash-pin the central training-inference knob registry when declared."""

    raw = spec.knob_registry
    if raw is None:
        return {
            "enabled": False,
            "evidence": {
                "mode": "legacy_inline_contract_no_registry",
                "registry_path": str(DEFAULT_KNOB_REGISTRY).replace("\\", "/"),
            },
        }
    if not isinstance(raw, Mapping):
        raise ValueError("viv_slm_layer_campaign_knob_registry_invalid")
    registry_value = str(raw.get("path") or "").strip()
    expected_hash = str(raw.get("sha256") or "").strip()
    if not registry_value or len(expected_hash) != 64:
        raise ValueError("viv_slm_layer_campaign_knob_registry_binding_missing")
    registry_path = _required_file(_resolve_path(registry_value), "knob_registry")
    actual_hash = _sha256(registry_path)
    if actual_hash.casefold() != expected_hash.casefold():
        raise ValueError(f"viv_slm_layer_campaign_knob_registry_hash_mismatch:{actual_hash}")
    registry = _read_json(registry_path)
    if str(registry.get("schema_version") or "") != "viv_training_knob_registry_v1":
        raise ValueError("viv_slm_layer_campaign_knob_registry_schema_invalid")
    return {
        "enabled": True,
        "registry": registry,
        "evidence": {
            "mode": "hash_pinned_central_training_inference_registry",
            "registry_path": str(registry_path).replace("\\", "/"),
            "registry_sha256": actual_hash,
            "registry_schema_version": registry["schema_version"],
            "registry_status": registry.get("status"),
        },
    }


def _knob_float_matches(actual: Any, expected: Any) -> bool:
    try:
        return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12)
    except (TypeError, ValueError):
        return False


def _validate_knob_registry_binding(
    spec: LayerCampaignSpec,
    knob_registry: Mapping[str, Any],
    *,
    input_manifest: Mapping[str, Any],
) -> None:
    """Require a declared contract to agree with the central knob snapshot."""

    if not bool(knob_registry.get("enabled")):
        return
    registry = knob_registry.get("registry")
    if not isinstance(registry, Mapping):
        raise ValueError("viv_slm_layer_campaign_knob_registry_payload_missing")

    bounded = registry.get("bounded_training")
    if not isinstance(bounded, Mapping):
        raise ValueError("viv_slm_layer_campaign_knob_registry_bounded_training_missing")
    if int(spec.step_budget) != int(bounded.get("step_budget")):
        raise ValueError("viv_slm_layer_campaign_knob_registry_step_budget_mismatch")
    if int(spec.authority_scope.get("step_increment")) != int(bounded.get("step_increment")):
        raise ValueError("viv_slm_layer_campaign_knob_registry_step_increment_mismatch")
    if int(_config(spec, "evaluation_interval", -1)) != int(bounded.get("evaluation_interval")):
        raise ValueError("viv_slm_layer_campaign_knob_registry_evaluation_interval_mismatch")
    if int(spec.rollback_budget) != int(bounded.get("rollback_budget")):
        raise ValueError("viv_slm_layer_campaign_knob_registry_rollback_budget_mismatch")

    composition = registry.get("composition")
    expected_scales = list(composition.get("scale_ladder") or ()) if isinstance(composition, Mapping) else []
    if list(spec.allowed_scale_ladder) != expected_scales:
        raise ValueError("viv_slm_layer_campaign_knob_registry_composition_ladder_mismatch")

    metric_guards = registry.get("metric_guards")
    if not isinstance(metric_guards, Mapping):
        raise ValueError("viv_slm_layer_campaign_knob_registry_metric_guards_missing")
    for key in ("validation_nll_tolerance", "validation_accuracy_tolerance", "teacher_kl_tolerance"):
        if not _knob_float_matches(spec.metric_guards.get(key), metric_guards.get(key)):
            raise ValueError(f"viv_slm_layer_campaign_knob_registry_metric_guard_mismatch:{key}")

    probe_suite = list(registry.get("probe_suite") or ())
    if list(spec.probe_suite) != probe_suite:
        raise ValueError("viv_slm_layer_campaign_knob_registry_probe_suite_mismatch")

    optimizer_defaults = registry.get("optimizer_defaults")
    if not isinstance(optimizer_defaults, Mapping):
        raise ValueError("viv_slm_layer_campaign_knob_registry_optimizer_defaults_missing")
    optimizer_fields = ("batch_size", "eval_batch_size", "learning_rate", "weight_decay", "max_grad_norm", "seed", "sample_tokens", "top_k")
    for key in optimizer_fields:
        if key not in spec.training_config or not _knob_float_matches(spec.training_config.get(key), optimizer_defaults.get(key)):
            raise ValueError(f"viv_slm_layer_campaign_knob_registry_optimizer_mismatch:{key}")

    controller = registry.get("controller")
    controller_config = _config(spec, "controller_tuning", None)
    if not isinstance(controller, Mapping) or not isinstance(controller_config, Mapping):
        raise ValueError("viv_slm_layer_campaign_knob_registry_controller_missing")
    for key in ("schema_version", "ema_alpha", "teacher_kl_delta_target", "validation_nll_delta_target", "loss_relative_tolerance", "grad_norm_target_ratio"):
        expected = controller.get(key)
        actual = controller_config.get(key)
        if key == "schema_version":
            matches = str(actual) == str(expected)
        else:
            matches = _knob_float_matches(actual, expected)
        if not matches:
            raise ValueError(f"viv_slm_layer_campaign_knob_registry_controller_mismatch:{key}")

    bounds = registry.get("actuator_bounds")
    if not isinstance(bounds, Mapping):
        raise ValueError("viv_slm_layer_campaign_knob_registry_actuator_bounds_missing")
    bound_fields = {
        "anchor_weight": ("anchor_weight_min", "anchor_weight_max"),
        "learning_rate_scale": ("learning_rate_scale_min", "learning_rate_scale_max"),
        "gradient_clip_scale": ("gradient_clip_scale_min", "gradient_clip_scale_max"),
        "weight_decay_scale": ("weight_decay_scale_min", "weight_decay_scale_max"),
    }
    for name, (minimum_key, maximum_key) in bound_fields.items():
        profile = bounds.get(name)
        if not isinstance(profile, Mapping):
            raise ValueError(f"viv_slm_layer_campaign_knob_registry_actuator_missing:{name}")
        if not _knob_float_matches(_config(spec, minimum_key, None), profile.get("min")):
            raise ValueError(f"viv_slm_layer_campaign_knob_registry_actuator_min_mismatch:{name}")
        if not _knob_float_matches(_config(spec, maximum_key, None), profile.get("max")):
            raise ValueError(f"viv_slm_layer_campaign_knob_registry_actuator_max_mismatch:{name}")
    if not _knob_float_matches(_config(spec, "anchor_weight", None), bounds["anchor_weight"].get("initial")):
        raise ValueError("viv_slm_layer_campaign_knob_registry_anchor_initial_mismatch")

    inference_profile = registry.get("training_inference_profile")
    if not isinstance(inference_profile, Mapping):
        raise ValueError("viv_slm_layer_campaign_knob_registry_training_inference_profile_missing")
    generation = inference_profile.get("generation")
    if not isinstance(generation, Mapping):
        raise ValueError("viv_slm_layer_campaign_knob_registry_training_generation_missing")
    if int(_config(spec, "sample_tokens", -1)) != int(generation.get("sample_tokens")):
        raise ValueError("viv_slm_layer_campaign_knob_registry_sample_tokens_mismatch")
    if int(_config(spec, "top_k", -1)) != int(generation.get("top_k")):
        raise ValueError("viv_slm_layer_campaign_knob_registry_top_k_mismatch")
    expected_termination = str(inference_profile.get("termination_marker") or "")
    if str(input_manifest.get("termination_marker") or "") != expected_termination:
        raise ValueError("viv_slm_layer_campaign_knob_registry_termination_marker_mismatch")


def _load_controller_state_seed(spec: LayerCampaignSpec) -> dict[str, Any]:
    raw = _config(spec, "controller_state_seed", None)
    controller_config = dict(_config(spec, "controller_tuning", {}) or {})
    expected_schema = str(controller_config.get("schema_version") or "viv_slm_multi_metric_controller_v1")
    if raw is None:
        return {
            "enabled": False,
            "expected_schema_version": expected_schema,
            "evidence": {
                "mode": "fresh_defaults",
                "metric_history_carried": False,
            },
        }
    if not isinstance(raw, Mapping) or str(raw.get("mode") or "").strip() != "carry_forward_actuation_only":
        raise ValueError("viv_slm_layer_campaign_controller_state_seed_mode_invalid")
    manifest_value = str(raw.get("source_run_manifest") or "").strip()
    expected_manifest_hash = str(raw.get("source_run_manifest_sha256") or "").strip()
    expected_checkpoint_hash = str(raw.get("source_checkpoint_sha256") or "").strip()
    if not manifest_value or len(expected_manifest_hash) != 64 or len(expected_checkpoint_hash) != 64:
        raise ValueError("viv_slm_layer_campaign_controller_state_seed_binding_missing")
    manifest_path = _required_file(_resolve_path(manifest_value), "controller_state_seed_manifest")
    actual_manifest_hash = _sha256(manifest_path)
    if actual_manifest_hash.casefold() != expected_manifest_hash.casefold():
        raise ValueError(f"viv_slm_layer_campaign_controller_state_seed_manifest_hash_mismatch:{actual_manifest_hash}")
    source_manifest = _read_json(manifest_path)
    source_checkpoint_hash = str(source_manifest.get("checkpoint_sha256") or "").strip()
    if source_checkpoint_hash.casefold() != expected_checkpoint_hash.casefold():
        raise ValueError("viv_slm_layer_campaign_controller_state_seed_checkpoint_hash_mismatch")
    if expected_checkpoint_hash.casefold() != spec.parent_checkpoint_sha256.casefold():
        raise ValueError("viv_slm_layer_campaign_controller_state_seed_parent_binding_mismatch")
    source_state = source_manifest.get("controller_final")
    if not isinstance(source_state, Mapping):
        raise ValueError("viv_slm_layer_campaign_controller_state_seed_controller_missing")
    source_schema = str(source_state.get("schema_version") or "").strip()
    if source_schema != expected_schema:
        raise ValueError("viv_slm_layer_campaign_controller_state_seed_schema_mismatch")
    source_layer_id = str(raw.get("source_layer_id") or "").strip()
    evidence = {
        "mode": "carry_forward_actuation_only",
        "metric_history_carried": False,
        "source_run_manifest": str(manifest_path).replace("\\", "/"),
        "source_run_manifest_sha256": actual_manifest_hash,
        "source_checkpoint_sha256": expected_checkpoint_hash.upper(),
        "source_layer_id": source_layer_id,
        "source_controller_schema_version": source_schema,
        "seeded_fields": ["anchor_weight", "gradient_clip_scale", "lr_scale", "weight_decay_scale"],
    }
    return {
        "enabled": True,
        "expected_schema_version": expected_schema,
        "source_state": dict(source_state),
        "evidence": evidence,
    }


def _required_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"viv_slm_layer_campaign_{label}_missing:{path}")
    return path


def _verify_checkpoint(path_value: str, expected_hash: str, label: str) -> dict[str, str]:
    path = _required_file(_resolve_path(path_value), label)
    actual = _sha256(path)
    if actual.casefold() != expected_hash.casefold():
        raise ValueError(f"viv_slm_layer_campaign_{label}_hash_mismatch:{actual}")
    return {"path": str(path).replace("\\", "/"), "sha256": actual}


def _load_state(path: Path, label: str) -> dict[str, torch.Tensor]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != base.CHECKPOINT_SCHEMA:
        raise ValueError(f"viv_slm_layer_campaign_{label}_checkpoint_schema_invalid:{path}")
    state = checkpoint.get("best_model_state_dict") or checkpoint.get("model_state_dict")
    if not isinstance(state, Mapping):
        raise ValueError(f"viv_slm_layer_campaign_{label}_checkpoint_state_missing:{path}")
    return {str(key): value.detach().cpu().clone() for key, value in state.items()}


def _closed_authority_value(record: Mapping[str, Any], field: str) -> Any:
    value = record.get(field)
    if value is not None:
        return value
    aliases = {"deployment_changed": "deployment_authorized"}
    for nested_key in ("authorization", "authority"):
        nested = record.get(nested_key)
        if isinstance(nested, Mapping):
            value = nested.get(field, nested.get(aliases.get(field, "")))
            if value is not None:
                return value
    return None


def _normalized_authority_record(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    for field in (
        "training_authorized",
        "run_authorized",
        "promotion_authorized",
        "deployment_changed",
        "live_model_changed",
        "global_aifl_writes",
        "master_s_n_mutation",
        "knowledge_admission",
    ):
        if field not in normalized:
            value = _closed_authority_value(record, field)
            if value is not None:
                normalized[field] = value
    return normalized


def _validate_closed_side_effects(record: Mapping[str, Any]) -> None:
    for field in (
        "promotion_authorized",
        "deployment_changed",
        "live_model_changed",
        "global_aifl_writes",
        "master_s_n_mutation",
        "knowledge_admission",
    ):
        if _closed_authority_value(record, field) is not False:
            raise PermissionError(f"viv_slm_layer_campaign_side_effect_gate_open:{field}")


def _load_inputs(spec: LayerCampaignSpec) -> tuple[Any, dict[str, Any], Path, dict[str, str]]:
    input_root = _resolve_path(spec.input_root)
    tokenizer, manifest, tensor_dir = base._validate_input(input_root)
    if manifest.get("training_authorized") is not False or manifest.get("run_authorized") is not False:
        raise ValueError("viv_slm_layer_campaign_input_authority_flags_open")
    if manifest.get("world_knowledge_included") is not False or manifest.get("response_only_loss") is not True:
        raise ValueError("viv_slm_layer_campaign_input_policy_invalid")
    input_manifest_path = input_root / "INPUT_MANIFEST.json"
    vocab_path = input_root / "VOCAB.json"
    tensor_manifest_path = tensor_dir / "MANIFEST.json"
    evidence = {
        "input_manifest": str(input_manifest_path).replace("\\", "/"),
        "input_manifest_sha256": _sha256(input_manifest_path),
        "vocab_file": str(vocab_path).replace("\\", "/"),
        "vocab_file_sha256": _sha256(vocab_path),
        "tensor_manifest": str(tensor_manifest_path).replace("\\", "/"),
        "tensor_manifest_sha256": _sha256(tensor_manifest_path),
    }
    return tokenizer, manifest, tensor_dir, evidence


def _prepare_campaign(
    *,
    contract_path: Path,
    task_path: Path,
    ledger_path: Path,
    output_dir: Path,
    steps: int,
    authorize: bool,
) -> dict[str, Any]:
    spec = validate_layer_campaign_spec(_read_json(contract_path))
    knob_registry = _load_knob_registry(spec)
    require_one_increment(steps)
    if spec.step_budget != steps:
        raise PermissionError("viv_slm_layer_campaign_contract_step_budget_mismatch")
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_layer_campaign_output_exists_refuse_overwrite:{output_dir}")
    record = supervisor.load_task_record(task_path, spec.campaign_id)
    ledger = _read_json(ledger_path)
    parent = supervisor.select_parent_layer(ledger, task_record=record)
    parent_checkpoint = str(_resolve_path(str(parent.get("checkpoint") or ""))).replace("\\", "/").casefold()
    spec_parent_checkpoint = str(_resolve_path(spec.parent_checkpoint)).replace("\\", "/").casefold()
    if str(parent.get("checkpoint_sha256") or "").casefold() != spec.parent_checkpoint_sha256.casefold():
        raise PermissionError("viv_slm_layer_campaign_ledger_parent_hash_mismatch")
    if parent_checkpoint != spec_parent_checkpoint:
        raise PermissionError("viv_slm_layer_campaign_ledger_parent_path_mismatch")
    if record.get("campaign_id") != spec.campaign_id:
        raise PermissionError("viv_slm_layer_campaign_task_campaign_mismatch")
    if str(record.get("parent_checkpoint_sha256") or "").casefold() not in ("", spec.parent_checkpoint_sha256.casefold()):
        raise PermissionError("viv_slm_layer_campaign_task_parent_hash_mismatch")
    _validate_closed_side_effects(record)
    normalized_record = _normalized_authority_record(record)
    if authorize:
        authority = validate_authority_record(normalized_record, campaign_id=spec.campaign_id, steps=steps)
    else:
        if normalized_record.get("scope", {}).get("steps") != steps:
            raise PermissionError("viv_slm_layer_campaign_task_scope_steps_mismatch")
        authority = {
            "campaign_id": spec.campaign_id,
            "steps": steps,
            "training_authorized": normalized_record.get("training_authorized"),
            "run_authorized": normalized_record.get("run_authorized"),
            "promotion_authorized": False,
            "deployment_changed": False,
            "live_model_changed": False,
            "global_aifl_writes": False,
            "master_s_n_mutation": False,
            "knowledge_admission": False,
        }
    source_evidence = {
        "parent": _verify_checkpoint(spec.parent_checkpoint, spec.parent_checkpoint_sha256, "parent_checkpoint"),
        "delta_source_parent": _verify_checkpoint(spec.delta_source_parent, spec.delta_source_parent_sha256, "delta_source_parent"),
        "delta_source_child": _verify_checkpoint(spec.delta_source_child, spec.delta_source_child_sha256, "delta_source_child"),
        "teacher_reference": _verify_checkpoint(spec.teacher_reference_checkpoint, spec.teacher_reference_checkpoint_sha256, "teacher_reference_checkpoint"),
    }
    tokenizer, input_manifest, tensor_dir, input_evidence = _load_inputs(spec)
    _validate_knob_registry_binding(spec, knob_registry, input_manifest=input_manifest)
    probes = []
    for probe in spec.probe_suite:
        probe_path = _required_file(_resolve_path(probe), "probe")
        probes.append({"path": str(probe_path).replace("\\", "/"), "sha256": _sha256(probe_path)})
    controller_state_seed = _load_controller_state_seed(spec)
    return {
        "spec": spec,
        "contract_sha256": _sha256(contract_path),
        "record": record,
        "ledger": ledger,
        "parent": parent,
        "authority": authority,
        "source_evidence": source_evidence,
        "input_evidence": input_evidence,
        "tokenizer": tokenizer,
        "input_manifest": input_manifest,
        "tensor_dir": tensor_dir,
        "probes": probes,
        "knob_registry": knob_registry,
        "controller_state_seed": controller_state_seed,
        "output_dir": output_dir,
    }


def build_campaign_plan(
    *,
    contract_path: Path = DEFAULT_CONTRACT,
    task_path: Path = DEFAULT_TASK,
    ledger_path: Path = DEFAULT_LEDGER,
    output_dir: Path | None = None,
    steps: int = 250,
) -> dict[str, Any]:
    """Validate a contract and emit a side-effect-free execution plan."""

    raw_contract = _read_json(contract_path)
    spec = validate_layer_campaign_spec(raw_contract)
    chosen_output = output_dir or (_resolve_path(spec.output_dir) if spec.output_dir else VIV_ROOT / "models" / "_UNSPECIFIED_LAYER_OUTPUT")
    prepared = _prepare_campaign(
        contract_path=contract_path,
        task_path=task_path,
        ledger_path=ledger_path,
        output_dir=chosen_output,
        steps=steps,
        authorize=False,
    )
    return {
        "schema_version": ENGINE_SCHEMA_VERSION,
        "status": "DRY_RUN_READY",
        "engine": "run_viv_slm_layer_campaign.py",
        "campaign": spec.to_mapping(),
        "contract_sha256": prepared["contract_sha256"],
        "parent_layer_id": prepared["parent"].get("layer_id"),
        "parent_checkpoint_sha256": prepared["parent"].get("checkpoint_sha256"),
        "authority": prepared["authority"],
        "source_evidence": prepared["source_evidence"],
        "input_evidence": prepared["input_evidence"],
        "probe_evidence": prepared["probes"],
        "knob_registry": prepared["knob_registry"]["evidence"],
        "controller_state_seed": prepared["controller_state_seed"]["evidence"],
        "output_dir": str(chosen_output).replace("\\", "/"),
        "side_effects": {
            "training": False,
            "promotion": False,
            "deployment": False,
            "live_model_mutation": False,
            "global_aifl_writes": False,
            "master_s_n_mutation": False,
            "knowledge_admission": False,
        },
    }


def _masked_nll(logits: torch.Tensor, targets: torch.Tensor, masks: torch.Tensor) -> torch.Tensor:
    vocab_size = logits.shape[-1]
    flat_logits = logits.reshape(-1, vocab_size)
    flat_targets = targets.reshape(-1)
    flat_masks = masks.reshape(-1).bool()
    if not bool(flat_masks.any()):
        raise ValueError("viv_slm_layer_campaign_masked_loss_empty")
    return F.cross_entropy(flat_logits[flat_masks], flat_targets[flat_masks])


def _teacher_anchor_kl(student_logits: torch.Tensor, teacher_logits: torch.Tensor, masks: torch.Tensor) -> torch.Tensor:
    flat_masks = masks.reshape(-1).bool()
    student = student_logits.float().reshape(-1, student_logits.shape[-1])[flat_masks]
    teacher = teacher_logits.float().reshape(-1, teacher_logits.shape[-1])[flat_masks]
    if student.numel() == 0:
        raise ValueError("viv_slm_layer_campaign_teacher_anchor_empty")
    return F.kl_div(F.log_softmax(student, dim=-1), F.softmax(teacher, dim=-1), reduction="batchmean")


def _evaluate_teacher_alignment(
    student: torch.nn.Module,
    teacher: torch.nn.Module,
    inputs: torch.Tensor,
    masks: torch.Tensor,
    *,
    device: torch.device,
    batch_size: int,
) -> dict[str, Any]:
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
            total_kl += float(
                F.kl_div(
                    F.log_softmax(student_logits, dim=-1),
                    F.softmax(teacher_logits, dim=-1),
                    reduction="sum",
                )
            )
            total_tokens += int(batch_masks.sum())
    if was_training:
        student.train()
    if total_tokens <= 0:
        raise ValueError("viv_slm_layer_campaign_teacher_alignment_empty")
    return {"teacher_kl": total_kl / total_tokens, "tokens": total_tokens}


def _evaluate_candidate(
    model: torch.nn.Module,
    teacher: torch.nn.Module,
    inputs: torch.Tensor,
    targets: torch.Tensor,
    masks: torch.Tensor,
    *,
    device: torch.device,
    batch_size: int,
) -> dict[str, Any]:
    metrics = base._evaluate(model, inputs, targets, device=device, batch_size=batch_size, loss_masks=masks)
    alignment = _evaluate_teacher_alignment(model, teacher, inputs, masks, device=device, batch_size=batch_size)
    return {**metrics, **alignment}


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _adaptive_teacher_controller(
    state: Mapping[str, Any],
    *,
    observed_teacher_kl_delta: float,
    observed_validation_nll_delta: float,
    observed_training_nll: float,
    observed_sft_loss: float,
    observed_total_loss: float,
    observed_grad_norm_before_clip: float,
    max_grad_norm: float,
    spec: LayerCampaignSpec,
) -> dict[str, Any]:
    controller_config = dict(_config(spec, "controller_tuning", {}) or {})
    controller_config.setdefault("schema_version", "viv_slm_multi_metric_controller_v1")
    controller_config.setdefault("ema_alpha", _config(spec, "controller_alpha", 0.10))
    controller_config.setdefault("teacher_kl_delta_target", _config(spec, "target_teacher_kl_delta", 0.002))
    controller_config.setdefault("validation_nll_delta_target", _config(spec, "target_validation_delta", 0.001))
    return adaptive_controller_update(
        state,
        observations={
            "teacher_kl_delta": observed_teacher_kl_delta,
            "validation_nll_delta": observed_validation_nll_delta,
            "training_nll": observed_training_nll,
            "sft_loss": observed_sft_loss,
            "total_loss": observed_total_loss,
            "grad_norm_before_clip": observed_grad_norm_before_clip,
        },
        config=controller_config,
        max_grad_norm=max_grad_norm,
        base_anchor_weight=float(_config(spec, "anchor_weight", 0.20)),
        anchor_weight_min=float(_config(spec, "anchor_weight_min", 0.05)),
        anchor_weight_max=float(_config(spec, "anchor_weight_max", 0.50)),
        learning_rate_scale_min=float(_config(spec, "learning_rate_scale_min", 0.20)),
        learning_rate_scale_max=float(_config(spec, "learning_rate_scale_max", 1.05)),
        gradient_clip_scale_min=float(_config(spec, "gradient_clip_scale_min", 0.75)),
        gradient_clip_scale_max=float(_config(spec, "gradient_clip_scale_max", 1.00)),
        base_weight_decay=float(_config(spec, "weight_decay", 0.0)),
        weight_decay_scale_min=float(_config(spec, "weight_decay_scale_min", 0.25)),
        weight_decay_scale_max=float(_config(spec, "weight_decay_scale_max", 1.00)),
    )


def train(
    *,
    contract_path: Path = DEFAULT_CONTRACT,
    task_path: Path = DEFAULT_TASK,
    ledger_path: Path = DEFAULT_LEDGER,
    output_dir: Path | None = None,
    steps: int = 250,
    device_name: str | None = None,
    max_grad_norm: float | None = None,
    sample_tokens: int | None = None,
    top_k: int | None = None,
    authorize: bool = False,
) -> dict[str, Any]:
    """Execute one authorized declarative campaign increment."""

    if not authorize:
        raise PermissionError("viv_slm_layer_campaign_requires_explicit_authorize_flag")
    raw_spec = validate_layer_campaign_spec(_read_json(contract_path))
    chosen_output = output_dir or (_resolve_path(raw_spec.output_dir) if raw_spec.output_dir else None)
    if chosen_output is None:
        raise ValueError("viv_slm_layer_campaign_output_dir_required")
    prepared = _prepare_campaign(
        contract_path=contract_path,
        task_path=task_path,
        ledger_path=ledger_path,
        output_dir=chosen_output,
        steps=steps,
        authorize=True,
    )
    spec = prepared["spec"]
    tokenizer = prepared["tokenizer"]
    input_manifest = prepared["input_manifest"]
    tensor_dir = prepared["tensor_dir"]
    knob_registry_evidence = prepared["knob_registry"]["evidence"]
    config = spec.training_config
    batch_size = int(_config(spec, "batch_size", 64))
    eval_batch_size = int(_config(spec, "eval_batch_size", 64))
    learning_rate = float(_config(spec, "learning_rate", 0.0001))
    weight_decay = float(_config(spec, "weight_decay", 0.0))
    evaluation_interval = int(_config(spec, "evaluation_interval", 50))
    seed = int(_config(spec, "seed", 42))
    chosen_device_name = str(device_name or _config(spec, "device", DEFAULT_DEVICE))
    chosen_max_grad_norm = float(max_grad_norm if max_grad_norm is not None else _config(spec, "max_grad_norm", 1.0))
    chosen_sample_tokens = int(sample_tokens if sample_tokens is not None else _config(spec, "sample_tokens", 160))
    chosen_top_k = int(top_k if top_k is not None else _config(spec, "top_k", 40))
    if batch_size <= 0 or eval_batch_size <= 0 or learning_rate <= 0.0 or weight_decay < 0.0 or evaluation_interval <= 0 or chosen_max_grad_norm <= 0.0:
        raise ValueError("viv_slm_layer_campaign_training_config_invalid")
    device = torch.device(chosen_device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("viv_slm_layer_campaign_cuda_requested_but_unavailable")
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)

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
        raise ValueError("viv_slm_layer_campaign_response_only_masks_required")

    model = base._make_model(tokenizer.vocab_size, device=device)
    parent_path = _resolve_path(spec.parent_checkpoint)
    child_path = _resolve_path(spec.delta_source_child)
    delta_parent_path = _resolve_path(spec.delta_source_parent)
    teacher_path = _resolve_path(spec.teacher_reference_checkpoint)
    starting_sample = base._load_warm_start(parent_path, tokenizer=tokenizer, model=model)
    parent_state = base._cpu_state_dict(model)
    child_state = _load_state(child_path, "delta_source_child")
    delta_parent_state = _load_state(delta_parent_path, "delta_source_parent")
    teacher = base._make_model(tokenizer.vocab_size, device=device)
    base._load_warm_start(teacher_path, tokenizer=tokenizer, model=teacher)
    teacher.eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)

    def evaluate_state(state: Mapping[str, Any]) -> Mapping[str, Any]:
        model.load_state_dict(state, strict=True)
        return _evaluate_candidate(
            model,
            teacher,
            validation_inputs,
            validation_targets,
            validation_masks,
            device=device,
            batch_size=eval_batch_size,
        )

    nll_tolerance = float(spec.metric_guards.get("validation_nll_tolerance", 0.001))
    accuracy_tolerance = float(spec.metric_guards.get("validation_accuracy_tolerance", 0.0005))
    teacher_tolerance = float(spec.metric_guards.get("teacher_kl_tolerance", 0.002))

    def guard_state(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> Mapping[str, bool]:
        return {
            "metric_guard": float(candidate["nll"]) <= float(baseline["nll"]) + nll_tolerance
            and float(candidate["token_accuracy"]) >= float(baseline["token_accuracy"]) - accuracy_tolerance,
            "behavior_guard": float(candidate["teacher_kl"]) <= float(baseline["teacher_kl"]) + teacher_tolerance,
        }

    def improved_state(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
        return bool(
            float(candidate["nll"]) < float(baseline["nll"]) - 1e-9
            or float(candidate["token_accuracy"]) > float(baseline["token_accuracy"]) + 1e-9
            or float(candidate["teacher_kl"]) < float(baseline["teacher_kl"]) - 1e-9
        )

    composition = evaluate_scale_ladder(
        parent_state=parent_state,
        delta_source_child_state=child_state,
        delta_source_parent_state=delta_parent_state,
        allowed_scale_ladder=spec.allowed_scale_ladder,
        evaluate_candidate=evaluate_state,
        guard_candidate=guard_state,
        improvement_candidate=improved_state,
    )
    selected_state = composition["selected_state"]
    selected_scale = float(composition["selected_scale"])
    model.load_state_dict(selected_state, strict=True)
    selected_initial_metrics = _evaluate_candidate(
        model,
        teacher,
        validation_inputs,
        validation_targets,
        validation_masks,
        device=device,
        batch_size=eval_batch_size,
    )
    parent_validation_metrics = dict(composition["baseline_metrics"])
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    batch_generator = torch.Generator(device="cpu")
    batch_generator.manual_seed(seed + 360)
    termination_marker = str(input_manifest.get("termination_marker") or "<END>")
    history: list[dict[str, Any]] = []
    best_step = 0
    best_validation_nll = float(selected_initial_metrics["nll"])
    best_validation_accuracy = float(selected_initial_metrics["token_accuracy"])
    best_teacher_kl = float(selected_initial_metrics["teacher_kl"])
    best_state = base._cpu_state_dict(model)
    consecutive_guard_failures = 0
    halt_reason: str | None = None
    last_step = 0
    controller_state: dict[str, Any] = {
        "teacher_kl_delta_ema": 0.0,
        "validation_nll_delta_ema": 0.0,
        "anchor_weight": float(_config(spec, "anchor_weight", 0.20)),
        "lr_scale": 1.0,
    }
    controller_state_seed = prepared["controller_state_seed"]
    if bool(controller_state_seed["enabled"]):
        controller_state = seed_controller_actuation_state(
            controller_state,
            controller_state_seed["source_state"],
            expected_schema_version=str(controller_state_seed["expected_schema_version"]),
            anchor_weight_min=float(_config(spec, "anchor_weight_min", 0.05)),
            anchor_weight_max=float(_config(spec, "anchor_weight_max", 0.50)),
            learning_rate_scale_min=float(_config(spec, "learning_rate_scale_min", 0.20)),
            learning_rate_scale_max=float(_config(spec, "learning_rate_scale_max", 1.05)),
            gradient_clip_scale_min=float(_config(spec, "gradient_clip_scale_min", 0.75)),
            gradient_clip_scale_max=float(_config(spec, "gradient_clip_scale_max", 1.00)),
            weight_decay_scale_min=float(_config(spec, "weight_decay_scale_min", 0.25)),
            weight_decay_scale_max=float(_config(spec, "weight_decay_scale_max", 1.00)),
        )
    controller_state["controller_seed"] = dict(controller_state_seed["evidence"])
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
        total_loss = sft_loss + (anchor_weight * anchor_kl)
        total_loss.backward()
        effective_learning_rate = learning_rate * float(controller_state["lr_scale"])
        for group in optimizer.param_groups:
            group["lr"] = effective_learning_rate
        weight_decay_scale = float(controller_state.get("weight_decay_scale", 1.0))
        if not math.isfinite(weight_decay_scale) or weight_decay_scale < 0.0 or weight_decay_scale > 1.0:
            raise ValueError("viv_slm_layer_campaign_weight_decay_scale_invalid")
        effective_weight_decay = weight_decay * weight_decay_scale
        for group in optimizer.param_groups:
            group["weight_decay"] = effective_weight_decay
        gradient_clip_scale = float(controller_state.get("gradient_clip_scale", 1.0))
        if not math.isfinite(gradient_clip_scale) or gradient_clip_scale <= 0.0 or gradient_clip_scale > 1.0:
            raise ValueError("viv_slm_layer_campaign_gradient_clip_scale_invalid")
        effective_max_grad_norm = chosen_max_grad_norm * gradient_clip_scale
        grad_norm_before = float(torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=effective_max_grad_norm))
        grad_norm_after = math.sqrt(
            sum(float(parameter.grad.detach().float().pow(2).sum()) for parameter in model.parameters() if parameter.grad is not None)
        )
        optimizer.step()
        if step % evaluation_interval != 0 and step != steps:
            continue
        training_metrics = base._evaluate(model, train_inputs, train_targets, device=device, batch_size=eval_batch_size, loss_masks=train_masks)
        validation_metrics = _evaluate_candidate(
            model,
            teacher,
            validation_inputs,
            validation_targets,
            validation_masks,
            device=device,
            batch_size=eval_batch_size,
        )
        model.train()
        validation_delta = float(validation_metrics["nll"]) - float(parent_validation_metrics["nll"])
        teacher_kl_delta = float(validation_metrics["teacher_kl"]) - float(parent_validation_metrics["teacher_kl"])
        controller_state = _adaptive_teacher_controller(
            controller_state,
            observed_teacher_kl_delta=teacher_kl_delta,
            observed_validation_nll_delta=validation_delta,
            observed_training_nll=float(training_metrics["nll"]),
            observed_sft_loss=float(sft_loss.detach()),
            observed_total_loss=float(total_loss.detach()),
            observed_grad_norm_before_clip=grad_norm_before,
            max_grad_norm=chosen_max_grad_norm,
            spec=spec,
        )
        guards = guard_state(parent_validation_metrics, validation_metrics)
        improved = bool(
            float(validation_metrics["nll"]) < best_validation_nll - 1e-9
            or float(validation_metrics["token_accuracy"]) > best_validation_accuracy + 1e-9
            or float(validation_metrics["teacher_kl"]) < best_teacher_kl - 1e-9
        )
        selected = bool(all(guards.values()) and improved)
        decision = guarded_rollback_decision(
            guards=guards,
            consecutive_guard_failures=consecutive_guard_failures,
            max_consecutive_failures=spec.rollback_budget,
        )
        consecutive_guard_failures = int(decision["consecutive_guard_failures"])
        if selected:
            best_validation_nll = float(validation_metrics["nll"])
            best_validation_accuracy = float(validation_metrics["token_accuracy"])
            best_teacher_kl = float(validation_metrics["teacher_kl"])
            best_step = step
            best_state = base._cpu_state_dict(model)
        if bool(decision["rollback"]):
            model.load_state_dict(best_state, strict=True)
            optimizer.state.clear()
            optimizer.zero_grad(set_to_none=True)
        if bool(decision["halt"]):
            halt_reason = "consecutive_guard_failure_budget_exhausted"
        record = {
            "step": step,
            "training": training_metrics,
            "validation": validation_metrics,
            "parent_validation": parent_validation_metrics,
            "validation_nll_delta_vs_parent": validation_delta,
            "teacher_kl_delta_vs_parent": teacher_kl_delta,
            "guard_results": guards,
            "guarded_rollback": bool(decision["rollback"]),
            "consecutive_guard_failures": consecutive_guard_failures,
            "optimizer_state_reset": bool(decision["rollback"]),
            "halt_after_record": bool(decision["halt"]),
            "guard_decision_reason": decision["reason"],
            "selected_as_best": selected,
            "sft_loss": float(sft_loss.detach()),
            "anchor_kl": float(anchor_kl.detach()),
            "anchor_weight": anchor_weight,
            "effective_learning_rate": effective_learning_rate,
            "weight_decay_scale": weight_decay_scale,
            "effective_weight_decay": effective_weight_decay,
            "gradient_clip_scale": gradient_clip_scale,
            "effective_max_grad_norm": effective_max_grad_norm,
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

    model.load_state_dict(best_state, strict=True)
    model.eval()
    generations = [
        {
            "prompt": "Viv:",
            "temperature": temperature,
            "top_k": chosen_top_k,
            "generated_token_count": chosen_sample_tokens,
            "text": base._sample(
                model,
                tokenizer,
                device=device,
                temperature=temperature,
                top_k=chosen_top_k,
                max_new_tokens=chosen_sample_tokens,
                seed=seed + 460 + index,
                stop_marker=termination_marker,
            ),
            "stop_marker": termination_marker,
        }
        for index, temperature in enumerate((0.0, 0.25, 0.5, 0.75, 1.0))
    ]
    training_status = "complete" if halt_reason is None else "halted_guard_budget"
    objective = {
        "kind": "declarative_parent_bound_delta_composition_full_surface_teacher_anchor",
        "composition_scales": list(spec.allowed_scale_ladder),
        "selected_composition_scale": selected_scale,
        "metric_guards": dict(spec.metric_guards),
        "rollback_budget": spec.rollback_budget,
        "manual_adjustments_during_run": False,
        "engine_schema_version": ENGINE_SCHEMA_VERSION,
    }
    initialization_mode = (
        "declarative_parent_bound_delta_composition_controller_actuation_seeded"
        if bool(controller_state_seed["enabled"])
        else "declarative_parent_bound_delta_composition_fresh_optimizer"
    )
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
            **dict(config),
            "batch_size": batch_size,
            "eval_batch_size": eval_batch_size,
            "learning_rate": learning_rate,
            "weight_decay": weight_decay,
            "evaluation_interval": evaluation_interval,
            "max_grad_norm": chosen_max_grad_norm,
            "seed": seed,
            "device": str(device),
            "termination_marker": termination_marker,
            "response_only_loss": True,
            "initialization": initialization_mode,
            "objective": objective,
        },
        "input_manifest": input_manifest,
        "knob_registry": knob_registry_evidence,
        "source_evidence": {**prepared["source_evidence"], **prepared["input_evidence"]},
        "starting_sample": starting_sample,
        "composition_trials": composition["trials"],
        "selected_initial_metrics": selected_initial_metrics,
        "parent_validation_metrics": parent_validation_metrics,
        "best_validation_step": best_step,
        "best_validation_nll": best_validation_nll,
        "best_validation_token_accuracy": best_validation_accuracy,
        "best_teacher_kl": best_teacher_kl,
        "best_model_state_dict": best_state,
        "generation_comparison": generations,
        "model_state_dict": base._cpu_state_dict(model),
        "optimizer_state_dict": optimizer.state_dict(),
        "controller_final": dict(controller_state),
        "controller_state_seed": controller_state_seed["evidence"],
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "global_aifl_writes": False,
        "master_s_n_mutation": False,
        "aios_live_mutation": False,
    }
    chosen_output.mkdir(parents=True, exist_ok=False)
    checkpoint_path = chosen_output / "checkpoint.pt"
    torch.save(checkpoint, checkpoint_path)
    run_manifest = {
        "schema_version": base.SCHEMA_VERSION,
        "engine_schema_version": ENGINE_SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED" if halt_reason is None else "HALTED_GUARD_BUDGET_CLOSED",
        "model": base.MODEL_NAME,
        "weights_status": "trained",
        "training_status": training_status,
        "campaign_id": spec.campaign_id,
        "training_steps": last_step,
        "requested_training_steps": steps,
        "halt_reason": halt_reason,
        "selected_state_step": best_step,
        "step_increment": 250,
        "evaluation_interval": evaluation_interval,
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "source_evidence": {**prepared["source_evidence"], **prepared["input_evidence"]},
        "knob_registry": knob_registry_evidence,
        "checkpoint": str(checkpoint_path).replace("\\", "/"),
        "checkpoint_sha256": _sha256(checkpoint_path),
        "learning_rate": learning_rate,
        "weight_decay": weight_decay,
        "optimizer": "AdamW",
        "max_grad_norm": chosen_max_grad_norm,
        "batch_size": batch_size,
        "eval_batch_size": eval_batch_size,
        "device": str(device),
        "seed": seed,
        "top_k": chosen_top_k,
        "sample_tokens": chosen_sample_tokens,
        "response_only_loss": True,
        "warm_start_checkpoint": prepared["source_evidence"]["parent"]["path"],
        "warm_start_checkpoint_sha256": spec.parent_checkpoint_sha256,
        "delta_source_parent": prepared["source_evidence"]["delta_source_parent"]["path"],
        "delta_source_parent_sha256": spec.delta_source_parent_sha256,
        "delta_source_child": prepared["source_evidence"]["delta_source_child"]["path"],
        "delta_source_child_sha256": spec.delta_source_child_sha256,
        "teacher_reference_checkpoint": prepared["source_evidence"]["teacher_reference"]["path"],
        "teacher_reference_checkpoint_sha256": spec.teacher_reference_checkpoint_sha256,
        "objective": objective,
        "composition_trials": composition["trials"],
        "selected_composition_scale": selected_scale,
        "selected_initial_metrics": selected_initial_metrics,
        "parent_validation_metrics": parent_validation_metrics,
        "best_validation_step": best_step,
        "best_validation_nll": best_validation_nll,
        "best_validation_token_accuracy": best_validation_accuracy,
        "best_teacher_kl": best_teacher_kl,
        "controller_final": dict(controller_state),
        "controller_state_seed": controller_state_seed["evidence"],
        "training_authorized": True,
        "run_authorized": True,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "global_aifl_writes": False,
        "master_s_n_mutation": False,
        "knowledge_admission": False,
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "aios_live_mutation": False,
        "next_step": "run_external_probe_suite_before_any_working_parent_advance",
    }
    _json_write(chosen_output / "generation_comparison.json", {"samples": generations})
    _json_write(chosen_output / "training_history.json", {"measurements": history})
    _json_write(chosen_output / "RUN_MANIFEST.json", run_manifest)
    _json_write(
        chosen_output / "AUTHORIZATION.json",
        {
            "schema_version": "viv_slm_layer_campaign_authorization_v1",
            "campaign_id": spec.campaign_id,
            "contract_sha256": prepared["contract_sha256"],
            **prepared["authority"],
            "execution_completed": True,
            "promotion_authorized": False,
            "deployment_changed": False,
            "live_model_changed": False,
            "global_aifl_writes": False,
            "master_s_n_mutation": False,
            "knowledge_admission": False,
        },
    )
    return run_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--task", type=Path, default=DEFAULT_TASK)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--steps", type=int, default=250)
    parser.add_argument("--device")
    parser.add_argument("--max-grad-norm", type=float)
    parser.add_argument("--sample-tokens", type=int)
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--authorize", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        result = build_campaign_plan(
            contract_path=args.contract,
            task_path=args.task,
            ledger_path=args.ledger,
            output_dir=args.output_dir,
            steps=args.steps,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    result = train(
        contract_path=args.contract,
        task_path=args.task,
        ledger_path=args.ledger,
        output_dir=args.output_dir,
        steps=args.steps,
        device_name=args.device,
        max_grad_norm=args.max_grad_norm,
        sample_tokens=args.sample_tokens,
        top_k=args.top_k,
        authorize=args.authorize,
    )
    print(json.dumps({"status": "VIV_SLM_LAYER_CAMPAIGN_COMPLETE", **{key: result.get(key) for key in ("campaign_id", "checkpoint", "checkpoint_sha256", "training_steps", "training_status", "selected_composition_scale", "promotion_authorized", "deployment_changed")}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
