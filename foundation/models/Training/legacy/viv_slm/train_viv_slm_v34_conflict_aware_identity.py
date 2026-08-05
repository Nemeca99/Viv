#!/usr/bin/env python3
"""Run the governed V34 conflict-aware identity refinement canary.

V34 keeps V32 as the metric parent and reuses only the CPU-authorized V33
identity pairs.  It computes the identity/focus gradient and the replay
preservation gradient separately.  If the focus gradient conflicts with the
replay gradient, the conflicting component is projected out before the two
are combined.  A recursive bounded controller then nudges focus pressure,
replay pressure, and learning rate from measured conflict, replay loss drift,
and validation drift.  The best state is retained only under metric
guardrails; the final optimizer state is never allowed to replace a better
guarded model state. Guard failures trigger bounded rollback and optimizer
state reset so the loop can correct itself instead of compounding drift.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
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
import train_viv_slm_v33_pairwise_identity as v33  # noqa: E402
from lib.pairwise_objective import objective_values  # noqa: E402
from lib.viv_shadow_judge import load_criteria, score_draft  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

PAIRWISE_INPUT_ROOT = v33.PAIRWISE_INPUT_ROOT
REPLAY_INPUT_ROOT = v33.REPLAY_INPUT_ROOT
PARENT_CHECKPOINT = v33.PARENT_CHECKPOINT
V28_REFERENCE_CHECKPOINT = v33.V28_REFERENCE_CHECKPOINT
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v34_conflict_aware_identity" / "runs" / "conflict_aware_identity_steps_0250"
CURRENT_TASK = FOUNDATION / "artifacts" / "auto" / "agentic" / "CURRENT_TASK.json"

INPUT_SCHEMA_VERSION = "viv_slm_v33_pairwise_identity_inputs_v1"
INPUT_MANIFEST_SHA256 = "6091DD5B134C6ED7C524006DCC99DE3EC9EA7ADEE300CE0F59A10F00E960D5EC"
PAIRWISE_ROWS_SHA256 = "2BA367EE6B9989C067470790F3E321D93467F9910A90C7D0F8AF71F704A8C819"
PARENT_CHECKPOINT_SHA256 = "EC7065B19C6630B7CF3DD64AE78FD92371A02A4A4E7465EF3206AB6CE30EE2F9"
V28_REFERENCE_CHECKPOINT_SHA256 = "99D536EE2E0AB804B70B54B4C81C617468564F825EAE82E2F6296964796C1BF0"
REPLAY_INPUT_MANIFEST_SHA256 = "18446924D85E554A1D6452F011F88798CC4948D8D66CC021165C0B25F9953D72"
STEP_INCREMENT = 250
EVAL_INTERVAL = 50
BASE_LEARNING_RATE = 0.00002
LEARNING_RATE = BASE_LEARNING_RATE
CHOSEN_SFT_WEIGHT = 1.0
PAIRWISE_WEIGHT = 0.25
PAIRWISE_BETA = 1.0
PAIRWISE_MARGIN = 0.2
REPLAY_SFT_WEIGHT = 0.25
REPLAY_KL_WEIGHT = 0.25
BASE_FOCUS_SCALE = 0.10
MIN_FOCUS_SCALE = 0.01
MAX_FOCUS_SCALE = 0.12
MIN_LR_SCALE = 0.10
MAX_LR_SCALE = 1.05
MIN_REPLAY_SCALE = 1.00
MAX_REPLAY_SCALE = 4.00
CONTROLLER_ALPHA = 0.10
TARGET_REPLAY_NLL_DELTA = 0.002
TARGET_VALIDATION_NLL_DELTA = 0.001
VALIDATION_NLL_TOLERANCE = 0.001
VALIDATION_ACCURACY_TOLERANCE = 0.0005
SELECTION_MARGIN_NUDGE = 0.01
MAX_CONSECUTIVE_GUARD_FAILURES = 2
CAMPAIGN_ID = "viv_slm_identity_personality_v34_conflict_aware_identity_0250"
AIFL_DRAFT_TEMPERATURES = (0.0, 0.25, 0.5)
AIFL_MAX_NEW_TOKENS = 96
AIFL_SYNTHETIC_SN = 0.5
AIFL_FEEDBACK_INTENTS = ("greeting", "current_state")


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
        raise ValueError(f"viv_v34_expected_json_object:{path}")
    return value


def _validate_authority(*, authorize: bool, steps: int, learning_rate: float) -> dict[str, Any]:
    if not authorize:
        raise PermissionError("v34_conflict_aware_identity_requires_explicit_authorize_flag")
    if not CURRENT_TASK.is_file():
        raise FileNotFoundError(f"viv_v34_current_task_missing:{CURRENT_TASK}")
    task = _read_json(CURRENT_TASK)
    record = task.get("v34_conflict_aware_identity_training")
    if not isinstance(record, dict):
        raise PermissionError("v34_conflict_aware_identity_task_authorization_record_missing")
    if record.get("training_authorized") is not True or record.get("run_authorized") is not True:
        raise PermissionError("v34_conflict_aware_identity_task_authorization_closed")
    if record.get("promotion_authorized") is not False or record.get("deployment_changed") is not False:
        raise PermissionError("v34_conflict_aware_identity_promotion_or_deployment_state_invalid")
    scope = record.get("scope")
    if not isinstance(scope, dict) or int(scope.get("steps", -1)) != steps:
        raise PermissionError("v34_conflict_aware_identity_scope_steps_invalid")
    if not math.isclose(float(scope.get("learning_rate", -1.0)), learning_rate, rel_tol=0.0, abs_tol=1e-12):
        raise PermissionError("v34_conflict_aware_identity_scope_learning_rate_invalid")
    if record.get("parent_checkpoint_sha256", "").casefold() != PARENT_CHECKPOINT_SHA256.casefold():
        raise PermissionError("v34_conflict_aware_identity_parent_authority_hash_invalid")
    return {
        "campaign_id": CAMPAIGN_ID,
        "task_updated_utc": str(task.get("updated_utc") or ""),
        "parent_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
        "parent_checkpoint_sha256": PARENT_CHECKPOINT_SHA256,
        "training_authorized": True,
        "run_authorized": True,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
    }


def _validate_sources() -> tuple[CharacterTokenizer, dict[str, Any], Path, dict[str, Any]]:
    input_manifest_path = PAIRWISE_INPUT_ROOT / "INPUT_MANIFEST.json"
    rows_path = PAIRWISE_INPUT_ROOT / "PAIRWISE_ROWS.jsonl"
    if not input_manifest_path.is_file() or not rows_path.is_file():
        raise FileNotFoundError("viv_v34_pairwise_inputs_missing")
    input_manifest = _read_json(input_manifest_path)
    if input_manifest.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise ValueError("viv_v34_pairwise_input_schema_mismatch")
    if _sha256(input_manifest_path) != INPUT_MANIFEST_SHA256:
        raise ValueError("viv_v34_pairwise_input_manifest_hash_mismatch")
    if input_manifest.get("training_authorized") is not False or input_manifest.get("run_authorized") is not False:
        raise ValueError("viv_v34_pairwise_input_authority_flags_changed")
    if input_manifest.get("world_knowledge_included") is not False:
        raise ValueError("viv_v34_pairwise_world_knowledge_policy_violation")
    if _sha256(PARENT_CHECKPOINT) != PARENT_CHECKPOINT_SHA256:
        raise ValueError("viv_v34_parent_checkpoint_hash_mismatch")
    if _sha256(V28_REFERENCE_CHECKPOINT) != V28_REFERENCE_CHECKPOINT_SHA256:
        raise ValueError("viv_v34_v28_reference_checkpoint_hash_mismatch")
    replay_tokenizer, replay_manifest, replay_tensor_dir = base._validate_input(REPLAY_INPUT_ROOT)
    if _sha256(REPLAY_INPUT_ROOT / "INPUT_MANIFEST.json") != REPLAY_INPUT_MANIFEST_SHA256:
        raise ValueError("viv_v34_replay_input_manifest_hash_mismatch")
    pair_rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if _sha256(rows_path) != PAIRWISE_ROWS_SHA256:
        raise ValueError("viv_v34_pairwise_rows_hash_mismatch")
    if len(pair_rows) != 2 or [row.get("intent_id") for row in pair_rows] != ["greeting", "current_state"]:
        raise ValueError("viv_v34_pairwise_rows_invalid")
    for row in pair_rows:
        if row.get("rejected_is_sft_target") is not False:
            raise ValueError("viv_v34_rejected_text_sft_policy_violation")
        if row.get("training_authorized") is not False or row.get("run_authorized") is not False:
            raise ValueError("viv_v34_pair_row_authority_flags_changed")
    return replay_tokenizer, replay_manifest, replay_tensor_dir, {
        "input_manifest": str(input_manifest_path).replace("\\", "/"),
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "pairwise_rows": str(rows_path).replace("\\", "/"),
        "pairwise_rows_sha256": _sha256(rows_path),
        "replay_input_manifest": str(REPLAY_INPUT_ROOT / "INPUT_MANIFEST.json").replace("\\", "/"),
        "replay_input_manifest_sha256": REPLAY_INPUT_MANIFEST_SHA256,
        "v28_reference_checkpoint_sha256": V28_REFERENCE_CHECKPOINT_SHA256,
    }


def _load_pair_samples(tokenizer: CharacterTokenizer) -> list[dict[str, Any]]:
    return v33._load_pair_samples(tokenizer)


def _load_aifl_feedback_cases() -> list[dict[str, Any]]:
    """Load feedback cases from the same CPU-authorized pair source as training.

    AIFL must not grow a second, hand-copied identity corpus.  The pair file is
    hash-locked by ``_validate_sources`` before training, and this helper keeps
    every feedback prompt and approved meaning tied to that source at runtime.
    """
    rows_path = PAIRWISE_INPUT_ROOT / "PAIRWISE_ROWS.jsonl"
    if _sha256(rows_path) != PAIRWISE_ROWS_SHA256:
        raise ValueError("viv_v34_aifl_feedback_source_hash_mismatch")
    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if [row.get("intent_id") for row in rows] != list(AIFL_FEEDBACK_INTENTS):
        raise ValueError("viv_v34_aifl_feedback_source_intents_invalid")
    cases: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("prompt") or not row.get("chosen"):
            raise ValueError("viv_v34_aifl_feedback_source_text_missing")
        if row.get("chosen_source") != "cpu_identity_router_authorized_text":
            raise ValueError("viv_v34_aifl_feedback_authorized_source_invalid")
        if row.get("rejected_is_sft_target") is not False:
            raise ValueError("viv_v34_aifl_feedback_rejected_target_policy_invalid")
        cases.append(
            {
                "intent_id": str(row["intent_id"]),
                "pair_id": str(row.get("pair_id") or ""),
                "prompt": str(row["prompt"]),
                "authorized": str(row["chosen"]),
                "authorized_source": str(row["chosen_source"]),
            }
        )
    return cases


def _masked_nll(logits: torch.Tensor, targets: torch.Tensor, masks: torch.Tensor) -> torch.Tensor:
    valid = masks.reshape(-1).bool()
    if not bool(valid.any()):
        raise ValueError("viv_v34_replay_mask_empty")
    return F.cross_entropy(logits.reshape(-1, logits.shape[-1])[valid], targets.reshape(-1)[valid])


def _replay_kl(student_logits: torch.Tensor, reference_logits: torch.Tensor) -> torch.Tensor:
    student_log_probs = F.log_softmax(student_logits.float(), dim=-1)
    reference_probs = F.softmax(reference_logits.float(), dim=-1)
    return F.kl_div(student_log_probs, reference_probs, reduction="batchmean")


def _capture_gradients(model: torch.nn.Module) -> dict[str, torch.Tensor]:
    result = {
        name: parameter.grad.detach().clone()
        for name, parameter in model.named_parameters()
        if parameter.grad is not None
    }
    return result


def _gradient_geometry(
    focus_gradients: Mapping[str, torch.Tensor],
    replay_gradients: Mapping[str, torch.Tensor],
) -> dict[str, float | bool]:
    names = set(focus_gradients) | set(replay_gradients)
    dot = 0.0
    focus_norm_sq = 0.0
    replay_norm_sq = 0.0
    for name in names:
        focus = focus_gradients.get(name)
        replay = replay_gradients.get(name)
        if focus is None:
            focus = torch.zeros_like(replay)
        if replay is None:
            replay = torch.zeros_like(focus)
        dot += float(torch.sum(focus.float() * replay.float()))
        focus_norm_sq += float(torch.sum(focus.float() * focus.float()))
        replay_norm_sq += float(torch.sum(replay.float() * replay.float()))
    focus_norm = math.sqrt(max(focus_norm_sq, 0.0))
    replay_norm = math.sqrt(max(replay_norm_sq, 0.0))
    cosine = dot / (focus_norm * replay_norm + 1e-12)
    return {
        "dot_product": dot,
        "focus_norm": focus_norm,
        "replay_norm": replay_norm,
        "cosine": cosine,
        "conflict": dot < 0.0,
    }


def project_conflicting_gradient(
    focus_gradients: Mapping[str, torch.Tensor],
    replay_gradients: Mapping[str, torch.Tensor],
) -> tuple[dict[str, torch.Tensor], dict[str, float | bool]]:
    """Project the focus gradient out of the replay-opposing direction."""
    geometry = _gradient_geometry(focus_gradients, replay_gradients)
    projected: dict[str, torch.Tensor] = {}
    replay_norm_sq = float(geometry["replay_norm"]) ** 2
    coefficient = float(geometry["dot_product"]) / (replay_norm_sq + 1e-12)
    for name, focus in focus_gradients.items():
        replay = replay_gradients.get(name)
        if replay is None:
            projected[name] = focus.clone()
        elif bool(geometry["conflict"]):
            projected[name] = focus - (coefficient * replay)
        else:
            projected[name] = focus.clone()
    geometry["projection_applied"] = bool(geometry["conflict"])
    geometry["projection_coefficient"] = coefficient if bool(geometry["conflict"]) else 0.0
    return projected, geometry


def _combine_gradients(
    model: torch.nn.Module,
    focus_gradients: Mapping[str, torch.Tensor],
    replay_gradients: Mapping[str, torch.Tensor],
    *,
    focus_scale: float,
    replay_scale: float,
) -> dict[str, torch.Tensor]:
    projected, geometry = project_conflicting_gradient(focus_gradients, replay_gradients)
    focus_norm = math.sqrt(sum(float(torch.sum(value.float() * value.float())) for value in projected.values()))
    replay_norm = float(geometry["replay_norm"])
    normalization = replay_norm / (focus_norm + 1e-12) if replay_norm > 0.0 else 1.0
    combined: dict[str, torch.Tensor] = {}
    for name, parameter in model.named_parameters():
        focus = projected.get(name)
        replay = replay_gradients.get(name)
        if focus is None:
            focus = torch.zeros_like(parameter)
        if replay is None:
            replay = torch.zeros_like(parameter)
        combined[name] = (replay_scale * replay) + (focus_scale * normalization * focus)
    return combined


def _set_gradients(model: torch.nn.Module, gradients: Mapping[str, torch.Tensor]) -> None:
    for name, parameter in model.named_parameters():
        value = gradients.get(name)
        parameter.grad = None if value is None else value


def recursive_conflict_nudge_update(
    state: Mapping[str, Any],
    *,
    observed_conflict_cosine: float,
    observed_replay_nll_delta: float,
    observed_validation_nll_delta: float,
    observed_aifl_feedback_error: float,
) -> dict[str, float | int | str | bool]:
    """Recursively update bounded pressures from measured interference."""
    alpha = float(state.get("alpha", CONTROLLER_ALPHA))
    conflict_ema = alpha * observed_conflict_cosine + (1.0 - alpha) * float(state.get("conflict_ema", 0.0))
    replay_delta_ema = alpha * observed_replay_nll_delta + (1.0 - alpha) * float(state.get("replay_delta_ema", 0.0))
    validation_delta_ema = alpha * observed_validation_nll_delta + (1.0 - alpha) * float(state.get("validation_delta_ema", 0.0))
    feedback_error_ema = alpha * observed_aifl_feedback_error + (1.0 - alpha) * float(state.get("feedback_error_ema", 0.0))
    conflict_pressure = _clip(max(0.0, -conflict_ema), 0.0, 1.0)
    replay_pressure = _clip(max(0.0, replay_delta_ema) / TARGET_REPLAY_NLL_DELTA, 0.0, 1.0)
    validation_pressure = _clip(max(0.0, validation_delta_ema) / TARGET_VALIDATION_NLL_DELTA, 0.0, 1.0)
    feedback_pressure = _clip(max(0.0, feedback_error_ema), 0.0, 1.0)
    focus_scale = _clip(
        BASE_FOCUS_SCALE * (1.0 + (0.50 * feedback_pressure) - (0.60 * conflict_pressure) - (0.40 * replay_pressure) - (0.60 * validation_pressure)),
        MIN_FOCUS_SCALE,
        MAX_FOCUS_SCALE,
    )
    lr_scale = _clip(
        1.0 + (0.15 * feedback_pressure) - (0.35 * conflict_pressure) - (0.35 * replay_pressure) - (0.50 * validation_pressure),
        MIN_LR_SCALE,
        MAX_LR_SCALE,
    )
    replay_scale = _clip(
        1.0 + (0.50 * replay_pressure) + (0.75 * validation_pressure),
        MIN_REPLAY_SCALE,
        MAX_REPLAY_SCALE,
    )
    return {
        "schema_version": "viv_slm_v34_recursive_conflict_controller_v1",
        "alpha": alpha,
        "conflict_ema": conflict_ema,
        "replay_delta_ema": replay_delta_ema,
        "validation_delta_ema": validation_delta_ema,
        "feedback_error_ema": feedback_error_ema,
        "conflict_pressure": conflict_pressure,
        "replay_pressure": replay_pressure,
        "validation_pressure": validation_pressure,
        "feedback_pressure": feedback_pressure,
        "focus_scale": focus_scale,
        "lr_scale": lr_scale,
        "replay_scale": replay_scale,
    }


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def guarded_rollback_decision(
    *,
    metric_guard: bool,
    feedback_guard: bool,
    consecutive_guard_failures: int,
) -> dict[str, bool | int | str]:
    """Decide whether to roll back or halt after an evaluation guard failure."""
    guard_ok = bool(metric_guard and feedback_guard)
    next_failures = 0 if guard_ok else int(consecutive_guard_failures) + 1
    rollback = not guard_ok
    halt = next_failures >= MAX_CONSECUTIVE_GUARD_FAILURES
    return {
        "guard_ok": guard_ok,
        "rollback": rollback,
        "halt": halt,
        "consecutive_guard_failures": next_failures,
        "reason": "guard_pass" if guard_ok else "metric_or_aifl_guard_failure",
    }


def _sample_prompt_reply(
    model: torch.nn.Module,
    tokenizer: CharacterTokenizer,
    *,
    prompt: str,
    device: torch.device,
    temperature: float,
    seed: int,
    stop_marker: str,
) -> str:
    """Generate one local draft without writing to the global AIFL buffers."""
    rendered_prompt = f"User: {prompt}\nViv: "
    prompt_ids = tokenizer.encode(rendered_prompt)
    ids = torch.tensor([prompt_ids], dtype=torch.long, device=device)
    generator = torch.Generator(device=device)
    generator.manual_seed(seed)
    with torch.no_grad():
        generated = model.generate(
            ids,
            max_new_tokens=AIFL_MAX_NEW_TOKENS,
            temperature=temperature,
            top_k=40,
            generator=generator,
        )
    text = tokenizer.decode(generated[0].detach().cpu().tolist())
    if rendered_prompt in text:
        text = text.split(rendered_prompt, 1)[1]
    if stop_marker and stop_marker in text:
        text = text.split(stop_marker, 1)[0]
    return text.strip()


def run_aifl_feedback(
    model: torch.nn.Module,
    tokenizer: CharacterTokenizer,
    *,
    device: torch.device,
    seed: int,
    stop_marker: str,
) -> dict[str, Any]:
    """Run the AIFL sensor locally as read-only internal feedback.

    This intentionally calls the existing CPU shadow-judge sensor directly,
    not ``judge_and_select``: the latter appends to the historical global
    preference buffer.  V34 records a run-local feedback pack instead, so the
    custom SLM lane cannot contaminate the older Qwen/OpenAster gate.
    """
    criteria = load_criteria()
    feedback_cases = _load_aifl_feedback_cases()
    cases: list[dict[str, Any]] = []
    was_training = bool(model.training)
    model.eval()
    for case_index, case in enumerate(feedback_cases):
        drafts: list[str] = []
        scored: list[dict[str, Any]] = []
        for draft_index, temperature in enumerate(AIFL_DRAFT_TEMPERATURES):
            draft = _sample_prompt_reply(
                model,
                tokenizer,
                prompt=str(case["prompt"]),
                device=device,
                temperature=float(temperature),
                seed=seed + 700 + (case_index * 10) + draft_index,
                stop_marker=stop_marker,
            )
            drafts.append(draft)
            scored.append(
                score_draft(
                    str(case["prompt"]),
                    draft,
                    facts=[f"know={case['prompt']}", f"know={case['authorized']}"],
                    context=f"CPU-authorized identity meaning: {case['authorized']}",
                    sn=AIFL_SYNTHETIC_SN,
                    criteria=criteria,
                )
            )
        mind_passes = [int(item.get("vidi") or 0) == 1 and int(item.get("intellexi") or 0) == 1 for item in scored]
        telemetry_clean = all(
            not any(term in str(draft).casefold() for term in ("master s_n", "telemetry", "security state"))
            for draft in drafts
        )
        unanimous = len(scored) == len(AIFL_DRAFT_TEMPERATURES) and all(mind_passes) and telemetry_clean
        cases.append(
            {
                "intent_id": case["intent_id"],
                "pair_id": case["pair_id"],
                "prompt": case["prompt"],
                "authorized_meaning": case["authorized"],
                "authorized_source": case["authorized_source"],
                "drafts": drafts,
                "scores": scored,
                "mind_passes": sum(1 for value in mind_passes if value),
                "draft_count": len(scored),
                "unanimous_alignment": unanimous,
                "telemetry_clean": telemetry_clean,
                "admission": "REWARD" if unanimous else "HOLD",
            }
        )
    total = max(1, len(cases) * len(AIFL_DRAFT_TEMPERATURES))
    mind_pass = sum(int(case["mind_passes"]) for case in cases)
    unanimous = sum(int(bool(case["unanimous_alignment"])) for case in cases)
    result = {
        "schema_version": "viv_slm_v34_aifl_feedback_pack_v1",
        "criteria_version": criteria.get("version"),
        "pairwise_rows_sha256": PAIRWISE_ROWS_SHA256,
        "draft_temperatures": list(AIFL_DRAFT_TEMPERATURES),
        "synthetic_sn": AIFL_SYNTHETIC_SN,
        "cases": cases,
        "mind_pass": mind_pass,
        "mind_total": total,
        "mind_pass_rate": mind_pass / total,
        "unanimous_cases": unanimous,
        "case_total": len(cases),
        "unanimous_rate": unanimous / max(1, len(cases)),
        "feedback_error": 1.0 - (mind_pass / total),
        "global_preference_buffer_written": False,
        "global_train_gate_written": False,
        "deployment_changed": False,
        "live_runtime_mutation": False,
        "status": "PASS" if unanimous == len(cases) else "HOLD",
    }
    model.train(was_training)
    return result


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
        raise ValueError("viv_v34_steps_must_be_positive_multiple_of_250")
    if not math.isclose(learning_rate, LEARNING_RATE, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("viv_v34_learning_rate_is_fixed_for_this_objective")
    if output_dir.exists():
        raise FileExistsError(f"viv_v34_output_exists_refuse_overwrite:{output_dir}")
    authority = _validate_authority(authorize=authorize, steps=steps, learning_rate=learning_rate)
    tokenizer, input_manifest, replay_tensor_dir, source_evidence = _validate_sources()
    pair_samples = _load_pair_samples(tokenizer)
    train_inputs, train_targets, train_masks = base._load_split(replay_tensor_dir, "train", vocab_size=tokenizer.vocab_size, response_only_loss=True)
    validation_inputs, validation_targets, validation_masks = base._load_split(replay_tensor_dir, "validation", vocab_size=tokenizer.vocab_size, response_only_loss=True)
    if train_masks is None or validation_masks is None:
        raise ValueError("viv_v34_replay_response_masks_required")
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("viv_v34_cuda_requested_but_unavailable")
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
    model = base._make_model(tokenizer.vocab_size, device=device)
    starting_sample = base._load_warm_start(PARENT_CHECKPOINT, tokenizer=tokenizer, model=model)
    reference = deepcopy(model).to(device)
    reference.eval()
    for parameter in reference.parameters():
        parameter.requires_grad_(False)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    batch_generator = torch.Generator(device="cpu")
    batch_generator.manual_seed(seed + 340)
    termination_marker = str(input_manifest.get("termination_marker") or "<END>")
    parent_validation_metrics = base._evaluate(reference, validation_inputs, validation_targets, device=device, batch_size=eval_batch_size, loss_masks=validation_masks)
    parent_aifl_feedback = run_aifl_feedback(reference, tokenizer, device=device, seed=seed + 600, stop_marker=termination_marker)
    history: list[dict[str, Any]] = []
    best_step = 0
    best_validation_nll = float(parent_validation_metrics["nll"])
    best_validation_accuracy = float(parent_validation_metrics["token_accuracy"])
    best_focus_margin = float("-inf")
    best_state: dict[str, torch.Tensor] = base._cpu_state_dict(model)
    latest_validation_delta = 0.0
    latest_aifl_feedback_error = float(parent_aifl_feedback["feedback_error"])
    consecutive_guard_failures = 0
    halt_reason: str | None = None
    last_step = 0
    controller_state: dict[str, float | int | str | bool] = {
        "schema_version": "viv_slm_v34_recursive_conflict_controller_v1",
        "alpha": CONTROLLER_ALPHA,
        "conflict_ema": 0.0,
        "replay_delta_ema": 0.0,
        "validation_delta_ema": 0.0,
        "feedback_error_ema": latest_aifl_feedback_error,
        "conflict_pressure": 0.0,
        "replay_pressure": 0.0,
        "validation_pressure": 0.0,
        "feedback_pressure": latest_aifl_feedback_error,
        "focus_scale": BASE_FOCUS_SCALE,
        "lr_scale": 1.0,
        "replay_scale": 1.0,
    }
    model.train()

    for step in range(1, steps + 1):
        last_step = step
        optimizer.zero_grad(set_to_none=True)
        pair_order = torch.randperm(len(pair_samples), generator=batch_generator).tolist()
        chosen_scores: list[torch.Tensor] = []
        rejected_scores: list[torch.Tensor] = []
        for index in pair_order:
            chosen_scores.append(v33._response_logp(model, pair_samples[index]["chosen_sample"], device=device))
            rejected_scores.append(v33._response_logp(model, pair_samples[index]["rejected_sample"], device=device))
        chosen_logp = torch.stack(chosen_scores)
        rejected_logp = torch.stack(rejected_scores)
        pair_values = objective_values(
            chosen_logp,
            rejected_logp,
            sft_weight=CHOSEN_SFT_WEIGHT,
            pairwise_weight=PAIRWISE_WEIGHT,
            beta=PAIRWISE_BETA,
            margin=PAIRWISE_MARGIN,
        )
        focus_loss = pair_values["loss"].mean()
        indices = torch.randint(0, train_inputs.shape[0], (batch_size,), generator=batch_generator)
        batch_inputs = train_inputs[indices].to(device)
        batch_targets = train_targets[indices].to(device)
        batch_masks = train_masks[indices].to(device)
        replay_logits = model(batch_inputs)
        with torch.no_grad():
            reference_logits = reference(batch_inputs)
        replay_nll = _masked_nll(replay_logits, batch_targets, batch_masks)
        anchor_kl = _replay_kl(replay_logits, reference_logits)
        replay_loss = (REPLAY_SFT_WEIGHT * replay_nll) + (REPLAY_KL_WEIGHT * anchor_kl)
        focus_loss.backward()
        focus_gradients = _capture_gradients(model)
        optimizer.zero_grad(set_to_none=True)
        replay_loss.backward()
        replay_gradients = _capture_gradients(model)
        geometry = _gradient_geometry(focus_gradients, replay_gradients)
        controller_state = recursive_conflict_nudge_update(
            controller_state,
            observed_conflict_cosine=float(geometry["cosine"]),
            observed_replay_nll_delta=float(replay_nll.detach() - _masked_nll(reference_logits, batch_targets, batch_masks).detach()),
            observed_validation_nll_delta=latest_validation_delta,
            observed_aifl_feedback_error=latest_aifl_feedback_error,
        )
        combined_gradients = _combine_gradients(
            model,
            focus_gradients,
            replay_gradients,
            focus_scale=float(controller_state["focus_scale"]),
            replay_scale=float(controller_state["replay_scale"]),
        )
        _set_gradients(model, combined_gradients)
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
        training_metrics = base._evaluate(model, train_inputs, train_targets, device=device, batch_size=eval_batch_size, loss_masks=train_masks)
        validation_metrics = base._evaluate(model, validation_inputs, validation_targets, device=device, batch_size=eval_batch_size, loss_masks=validation_masks)
        model.eval()
        aifl_feedback = run_aifl_feedback(model, tokenizer, device=device, seed=seed + 800 + step, stop_marker=termination_marker)
        model.train()
        validation_delta = float(validation_metrics["nll"]) - float(parent_validation_metrics["nll"])
        latest_validation_delta = validation_delta
        latest_aifl_feedback_error = float(aifl_feedback["feedback_error"])
        mean_margin = float((chosen_logp.detach() - rejected_logp.detach()).mean())
        metric_guard = (
            float(validation_metrics["nll"]) <= float(parent_validation_metrics["nll"]) + VALIDATION_NLL_TOLERANCE
            and float(validation_metrics["token_accuracy"]) >= float(parent_validation_metrics["token_accuracy"]) - VALIDATION_ACCURACY_TOLERANCE
        )
        feedback_guard = (
            float(aifl_feedback["mind_pass_rate"]) >= float(parent_aifl_feedback["mind_pass_rate"])
            and all(bool(case.get("telemetry_clean")) for case in aifl_feedback["cases"])
        )
        nll_improved = float(validation_metrics["nll"]) < best_validation_nll - 1e-9
        guarded_margin_improved = metric_guard and feedback_guard and mean_margin > best_focus_margin + SELECTION_MARGIN_NUDGE
        selected = bool(metric_guard and feedback_guard and (nll_improved or guarded_margin_improved))
        rollback_decision = guarded_rollback_decision(
            metric_guard=metric_guard,
            feedback_guard=feedback_guard,
            consecutive_guard_failures=consecutive_guard_failures,
        )
        consecutive_guard_failures = int(rollback_decision["consecutive_guard_failures"])
        if selected:
            best_validation_nll = float(validation_metrics["nll"])
            best_validation_accuracy = float(validation_metrics["token_accuracy"])
            best_focus_margin = mean_margin
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
            "aifl_feedback": aifl_feedback,
            "aifl_feedback_guard": feedback_guard,
            "guarded_rollback": bool(rollback_decision["rollback"]),
            "consecutive_guard_failures": consecutive_guard_failures,
            "optimizer_state_reset": bool(rollback_decision["rollback"]),
            "halt_after_record": bool(rollback_decision["halt"]),
            "guard_decision_reason": rollback_decision["reason"],
            "selected_as_best": selected,
            "pairwise": {
                "chosen_mean_logp": float(chosen_logp.detach().mean()),
                "rejected_mean_logp": float(rejected_logp.detach().mean()),
                "mean_margin": mean_margin,
                "pairwise_loss": float(pair_values["pairwise_loss"].detach().mean()),
                "pair_correct": int(pair_values["pair_correct"].detach().sum()),
            },
            "replay_nll": float(replay_nll.detach()),
            "anchor_kl": float(anchor_kl.detach()),
            "gradient_geometry": geometry,
            "effective_learning_rate": effective_learning_rate,
            "effective_focus_scale": float(controller_state["focus_scale"]),
            "effective_replay_scale": float(controller_state["replay_scale"]),
            "recursive_conflict_controller": dict(controller_state),
            "focus_loss": float(focus_loss.detach()),
            "replay_loss": float(replay_loss.detach()),
            "total_loss": float((focus_loss + replay_loss).detach()),
            "grad_norm_before_clip": grad_norm_before,
            "grad_norm_after_clip": grad_norm_after,
            "best_validation_step": best_step,
            "best_validation_nll": best_validation_nll,
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
            "text": base._sample(model, tokenizer, device=device, temperature=temperature, top_k=top_k, max_new_tokens=sample_tokens, seed=seed + 440 + index, stop_marker=termination_marker),
            "stop_marker": termination_marker,
        }
        for index, temperature in enumerate((0.0, 0.25, 0.5, 0.75, 1.0))
    ]
    checkpoint = {
        "schema_version": base.CHECKPOINT_SCHEMA,
        "model": base.MODEL_NAME,
        "weights_status": "trained",
        "training_status": "complete" if halt_reason is None else "halted_guard_budget",
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
            "initialization": "warm_start_v32_conflict_aware_fresh_optimizer",
            "warm_start_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
            "v28_behavior_reference_checkpoint": str(V28_REFERENCE_CHECKPOINT).replace("\\", "/"),
            "objective": {
                "kind": "conflict_projected_identity_focus_plus_replay_kl_and_sft",
                "chosen_sft_weight": CHOSEN_SFT_WEIGHT,
                "pairwise_weight": PAIRWISE_WEIGHT,
                "pairwise_beta": PAIRWISE_BETA,
                "pairwise_margin": PAIRWISE_MARGIN,
                "replay_sft_weight": REPLAY_SFT_WEIGHT,
                "replay_kl_weight": REPLAY_KL_WEIGHT,
                "base_focus_scale": BASE_FOCUS_SCALE,
                "gradient_projection": "remove_focus_component_opposing_replay_gradient",
                "automatic_adjustment": "recursive_conflict_replay_validation_bounded_nudge",
                "metric_guard": {
                    "validation_nll_tolerance": VALIDATION_NLL_TOLERANCE,
                    "validation_accuracy_tolerance": VALIDATION_ACCURACY_TOLERANCE,
                    "selection_margin_nudge": SELECTION_MARGIN_NUDGE,
                },
                "aifl_feedback": {
                    "sensor": "lib.viv_shadow_judge.score_draft",
                    "criteria_version": parent_aifl_feedback.get("criteria_version"),
                    "draft_temperatures": list(AIFL_DRAFT_TEMPERATURES),
                    "drafts_per_case": len(AIFL_DRAFT_TEMPERATURES),
                    "case_count": len(parent_aifl_feedback.get("cases") or []),
                    "source_pairwise_rows_sha256": PAIRWISE_ROWS_SHA256,
                    "global_preference_buffer_written": False,
                    "global_train_gate_written": False,
                    "synthetic_sn": AIFL_SYNTHETIC_SN,
                    "master_s_n_mutation": False,
                },
                "controller_final": dict(controller_state),
            },
        },
        "input_manifest": input_manifest,
        "source_evidence": source_evidence,
        "starting_sample": starting_sample,
        "training_history": history,
        "parent_validation_metrics": parent_validation_metrics,
        "parent_aifl_feedback": parent_aifl_feedback,
        "aifl_feedback_history": [record.get("aifl_feedback") for record in history],
        "guarded_rollback_history": [
            {
                "step": record.get("step"),
                "guarded_rollback": record.get("guarded_rollback"),
                "consecutive_guard_failures": record.get("consecutive_guard_failures"),
                "optimizer_state_reset": record.get("optimizer_state_reset"),
                "halt_after_record": record.get("halt_after_record"),
            }
            for record in history
        ],
        "best_validation_step": best_step,
        "best_validation_nll": best_validation_nll,
        "best_validation_accuracy": best_validation_accuracy,
        "best_model_state_dict": best_state,
        "generation_comparison": generations,
        "model_state_dict": base._cpu_state_dict(model),
        "optimizer_state_dict": optimizer.state_dict(),
        "aios_live_mutation": False,
        "knowledge_policy": "external_cpu_retrieval_only",
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_path = output_dir / "checkpoint.pt"
    torch.save(checkpoint, checkpoint_path)
    final = history[-1] if history else {}
    aifl_feedback_path = output_dir / "aifl_feedback.json"
    _json_write(
        aifl_feedback_path,
        {
            "schema_version": "viv_slm_v34_aifl_feedback_artifact_v1",
            "parent": parent_aifl_feedback,
            "measurements": [record.get("aifl_feedback") for record in history],
            "global_preference_buffer_written": False,
            "global_train_gate_written": False,
            "live_runtime_mutation": False,
            "deployment_changed": False,
        },
    )
    run_manifest = {
        "schema_version": base.SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED" if halt_reason is None else "HALTED_GUARD_BUDGET_CLOSED",
        "model": base.MODEL_NAME,
        "weights_status": "trained" if halt_reason is None else "halted_guard_budget",
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
        "pairwise_rows": source_evidence["pairwise_rows"],
        "pairwise_rows_sha256": source_evidence["pairwise_rows_sha256"],
        "replay_input_manifest": source_evidence["replay_input_manifest"],
        "replay_input_manifest_sha256": source_evidence["replay_input_manifest_sha256"],
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
        "v28_behavior_reference_checkpoint": str(V28_REFERENCE_CHECKPOINT).replace("\\", "/"),
        "v28_behavior_reference_checkpoint_sha256": V28_REFERENCE_CHECKPOINT_SHA256,
        "objective": checkpoint["training_config"]["objective"],
        "recursive_conflict_controller_final": dict(controller_state),
        "initial_or_final": final,
        "parent_validation_metrics": parent_validation_metrics,
        "parent_aifl_feedback": parent_aifl_feedback,
        "aifl_feedback_artifact": str(aifl_feedback_path).replace("\\", "/"),
        "aifl_feedback_artifact_sha256": _sha256(aifl_feedback_path),
        "aifl_feedback_global_preference_buffer_written": False,
        "aifl_feedback_global_train_gate_written": False,
        "aifl_feedback_live_runtime_mutation": False,
        "best_validation_step": best_step,
        "best_validation_nll": best_validation_nll,
        "best_validation_accuracy": best_validation_accuracy,
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "aios_live_mutation": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "next_step": "run_matched_identity_probes_and_cpu_boundary_before_any_promotion",
    }
    _json_write(output_dir / "generation_comparison.json", {"samples": generations})
    _json_write(output_dir / "training_history.json", {"measurements": history})
    _json_write(output_dir / "RUN_MANIFEST.json", run_manifest)
    (output_dir / "RUN_REPORT.md").write_text(
        "# Viv-SLM conflict-aware identity refinement run\n\n"
        f"- Completed optimizer steps: {last_step}\n"
        f"- Requested optimizer steps: {steps}\n"
        f"- Halt reason: {halt_reason or 'none'}\n"
        f"- Evaluation interval: {EVAL_INTERVAL}\n"
        f"- Selected state step: {best_step}\n"
        f"- Best validation NLL: {best_validation_nll}\n"
        f"- Best validation token accuracy: {best_validation_accuracy}\n"
        "- Gradient projection: focus components opposing replay were removed\n"
        f"- Parent AIFL mind-pass rate: {parent_aifl_feedback['mind_pass_rate']}\n"
        "- AIFL global preference/train-gate writes: false/false\n"
        "- Metric guard: active\n"
        "- World knowledge included: false\n"
        "- AIOS live mutation: false\n"
        "- Promotion/deployment: closed\n",
        encoding="utf-8",
        newline="\n",
    )
    _json_write(
        output_dir / "AUTHORIZATION.json",
        {
            "schema_version": "viv_slm_v34_training_authorization_v1",
            "campaign_id": CAMPAIGN_ID,
            "authorized_utc": authority["task_updated_utc"],
            "input_manifest_sha256": source_evidence["input_manifest_sha256"],
            "pairwise_rows_sha256": source_evidence["pairwise_rows_sha256"],
            "parent_checkpoint": authority["parent_checkpoint"],
            "parent_checkpoint_sha256": authority["parent_checkpoint_sha256"],
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
    run_manifest.update({
        "governance": authority,
        "training_authorized": True,
        "run_authorized": True,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
    })
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
    print(json.dumps({"status": "VIV_SLM_V34_CONFLICT_AWARE_IDENTITY_TRAINING_COMPLETE", "campaign_id": CAMPAIGN_ID, "checkpoint": result["checkpoint"], "training_steps": result["training_steps"], "selected_state_step": result["selected_state_step"], "best_validation_nll": result["best_validation_nll"], "learning_rate": LEARNING_RATE, "training_authorized": result["training_authorized"], "run_authorized": result["run_authorized"], "promotion_authorized": result["promotion_authorized"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
