#!/usr/bin/env python3
"""Run the governed V33 pairwise identity refinement canary.

V33 starts from V32, keeps a replay anchor against the V32 distribution, and
adds a small pairwise objective whose chosen responses are CPU-authorized
identity text and whose rejected responses are the observed V32 failures.  A
rejected response is used only in the preference term; it is never an SFT
target.  V28 remains a behavior reference for comparison, not a reset parent.
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
from lib.pairwise_objective import objective_values  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

PAIRWISE_INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v33_pairwise_identity" / "inputs"
REPLAY_INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v31_balanced_base" / "inputs"
PARENT_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v32_balanced_low_lr" / "runs" / "balanced_low_lr_steps_0250" / "checkpoint.pt"
V28_REFERENCE_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v28_canonical_disambiguation" / "runs" / "canonical_disambiguation_steps_0250" / "checkpoint.pt"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v33_pairwise_identity" / "runs" / "pairwise_identity_steps_0250"
CURRENT_TASK = FOUNDATION / "artifacts" / "auto" / "agentic" / "CURRENT_TASK.json"

INPUT_SCHEMA_VERSION = "viv_slm_v33_pairwise_identity_inputs_v1"
PARENT_CHECKPOINT_SHA256 = "EC7065B19C6630B7CF3DD64AE78FD92371A02A4A4E7465EF3206AB6CE30EE2F9"
V28_REFERENCE_CHECKPOINT_SHA256 = "99D536EE2E0AB804B70B54B4C81C617468564F825EAE82E2F6296964796C1BF0"
INPUT_MANIFEST_SHA256 = ""
REPLAY_INPUT_MANIFEST_SHA256 = "18446924D85E554A1D6452F011F88798CC4948D8D66CC021165C0B25F9953D72"
STEP_INCREMENT = 250
BASE_LEARNING_RATE = 0.00005
LEARNING_RATE = BASE_LEARNING_RATE
CHOSEN_SFT_WEIGHT = 1.0
PAIRWISE_WEIGHT = 0.75
PAIRWISE_BETA = 1.0
PAIRWISE_MARGIN = 0.2
REPLAY_SFT_WEIGHT = 0.25
REPLAY_ANCHOR_WEIGHT = 1.0
CONTROLLER_ALPHA = 0.1
CONTROLLER_TARGET_MARGIN = 0.2
CONTROLLER_TARGET_ANCHOR_DRIFT = 0.001
CONTROLLER_MIN_LR_SCALE = 0.25
CONTROLLER_MAX_LR_SCALE = 1.25
CONTROLLER_MIN_PAIRWISE_SCALE = 0.5
CONTROLLER_MAX_PAIRWISE_SCALE = 2.0
CONTROLLER_MIN_ANCHOR_SCALE = 0.75
CONTROLLER_MAX_ANCHOR_SCALE = 3.0
CAMPAIGN_ID = "viv_slm_identity_personality_v33_pairwise_identity_0250"


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
        raise ValueError(f"viv_v33_expected_json_object:{path}")
    return value


def _validate_authority(*, authorize: bool, steps: int, learning_rate: float) -> dict[str, Any]:
    if not authorize:
        raise PermissionError("v33_pairwise_identity_requires_explicit_authorize_flag")
    if not CURRENT_TASK.is_file():
        raise FileNotFoundError(f"viv_v33_current_task_missing:{CURRENT_TASK}")
    task = _read_json(CURRENT_TASK)
    record = task.get("v33_pairwise_identity_training")
    if not isinstance(record, dict):
        raise PermissionError("v33_pairwise_identity_task_authorization_record_missing")
    if record.get("training_authorized") is not True or record.get("run_authorized") is not True:
        raise PermissionError("v33_pairwise_identity_task_authorization_closed")
    if record.get("promotion_authorized") is not False or record.get("deployment_changed") is not False:
        raise PermissionError("v33_pairwise_identity_promotion_or_deployment_state_invalid")
    scope = record.get("scope")
    if not isinstance(scope, dict) or int(scope.get("steps", -1)) != steps:
        raise PermissionError("v33_pairwise_identity_scope_steps_invalid")
    if not math.isclose(float(scope.get("learning_rate", -1.0)), learning_rate, rel_tol=0.0, abs_tol=1e-12):
        raise PermissionError("v33_pairwise_identity_scope_learning_rate_invalid")
    if record.get("parent_checkpoint_sha256", "").casefold() != PARENT_CHECKPOINT_SHA256.casefold():
        raise PermissionError("v33_pairwise_identity_parent_authority_hash_invalid")
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
        raise FileNotFoundError("viv_v33_pairwise_inputs_missing")
    input_manifest = _read_json(input_manifest_path)
    if input_manifest.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise ValueError("viv_v33_pairwise_input_schema_mismatch")
    if input_manifest.get("training_authorized") is not False or input_manifest.get("run_authorized") is not False:
        raise ValueError("viv_v33_pairwise_input_authority_flags_changed")
    if input_manifest.get("world_knowledge_included") is not False:
        raise ValueError("viv_v33_pairwise_world_knowledge_policy_violation")
    if _sha256(PARENT_CHECKPOINT) != PARENT_CHECKPOINT_SHA256:
        raise ValueError("viv_v33_parent_checkpoint_hash_mismatch")
    if _sha256(V28_REFERENCE_CHECKPOINT) != V28_REFERENCE_CHECKPOINT_SHA256:
        raise ValueError("viv_v33_v28_reference_checkpoint_hash_mismatch")
    replay_tokenizer, replay_manifest, replay_tensor_dir = base._validate_input(REPLAY_INPUT_ROOT)
    if _sha256(REPLAY_INPUT_ROOT / "INPUT_MANIFEST.json") != REPLAY_INPUT_MANIFEST_SHA256:
        raise ValueError("viv_v33_replay_input_manifest_hash_mismatch")
    pair_rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(pair_rows) != 2 or [row.get("intent_id") for row in pair_rows] != ["greeting", "current_state"]:
        raise ValueError("viv_v33_pairwise_rows_invalid")
    for row in pair_rows:
        if row.get("rejected_is_sft_target") is not False:
            raise ValueError("viv_v33_rejected_text_sft_policy_violation")
        if row.get("training_authorized") is not False or row.get("run_authorized") is not False:
            raise ValueError("viv_v33_pair_row_authority_flags_changed")
    return replay_tokenizer, replay_manifest, replay_tensor_dir, {
        "input_manifest": str(input_manifest_path).replace("\\", "/"),
        "input_manifest_sha256": _sha256(input_manifest_path),
        "pairwise_rows": str(rows_path).replace("\\", "/"),
        "pairwise_rows_sha256": _sha256(rows_path),
        "replay_input_manifest": str(REPLAY_INPUT_ROOT / "INPUT_MANIFEST.json").replace("\\", "/"),
        "replay_input_manifest_sha256": REPLAY_INPUT_MANIFEST_SHA256,
        "v28_reference_checkpoint_sha256": V28_REFERENCE_CHECKPOINT_SHA256,
    }


def _encode_response(tokenizer: CharacterTokenizer, prompt: str, response: str) -> dict[str, torch.Tensor]:
    prefix = f"User: {prompt}\nViv: "
    text = f"{prefix}{response}\n<END>"
    response_start = len(prefix)
    if len(text) - 1 > base.MODEL_CONFIG["context_length"]:
        raise ValueError("viv_v33_pairwise_sequence_exceeds_context")
    character_mask = [False] * response_start + [True] * (len(text) - response_start)
    token_ids = tokenizer.encode(text)
    return {
        "inputs": torch.tensor(token_ids[:-1], dtype=torch.long),
        "targets": torch.tensor(token_ids[1:], dtype=torch.long),
        "loss_mask": torch.tensor(character_mask[1:], dtype=torch.bool),
    }


def _load_pair_samples(tokenizer: CharacterTokenizer) -> list[dict[str, Any]]:
    rows_path = PAIRWISE_INPUT_ROOT / "PAIRWISE_ROWS.jsonl"
    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    samples: list[dict[str, Any]] = []
    for row in rows:
        samples.append(
            {
                **row,
                "chosen_sample": _encode_response(tokenizer, str(row["prompt"]), str(row["chosen"])),
                "rejected_sample": _encode_response(tokenizer, str(row["prompt"]), str(row["rejected"])),
            }
        )
    return samples


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def recursive_nudge_update(state: Mapping[str, Any], *, observed_margin: float, observed_anchor_drift: float) -> dict[str, float | int | str]:
    """Update bounded controller state from the latest measured pattern.

    The exponential moving averages are recursive state: each nudge depends on
    the prior estimate and the newest observed signal.  The controller changes
    only scalar optimizer pressures and is clipped before they reach AdamW.
    """
    alpha = float(state.get("alpha", CONTROLLER_ALPHA))
    margin_ema = alpha * observed_margin + (1.0 - alpha) * float(state.get("margin_ema", 0.0))
    drift_ema = alpha * observed_anchor_drift + (1.0 - alpha) * float(state.get("anchor_drift_ema", 0.0))
    margin_error = CONTROLLER_TARGET_MARGIN - margin_ema
    drift_ratio = drift_ema / CONTROLLER_TARGET_ANCHOR_DRIFT if CONTROLLER_TARGET_ANCHOR_DRIFT else 0.0
    drift_excess = max(0.0, drift_ratio - 1.0)
    pairwise_scale = _clip(1.0 + (1.5 * margin_error), CONTROLLER_MIN_PAIRWISE_SCALE, CONTROLLER_MAX_PAIRWISE_SCALE)
    anchor_scale = _clip(1.0 + (0.5 * drift_excess), CONTROLLER_MIN_ANCHOR_SCALE, CONTROLLER_MAX_ANCHOR_SCALE)
    lr_scale = _clip(1.0 + (0.5 * margin_error) - (0.25 * drift_excess), CONTROLLER_MIN_LR_SCALE, CONTROLLER_MAX_LR_SCALE)
    return {
        "schema_version": "viv_slm_v33_recursive_nudge_controller_v1",
        "alpha": alpha,
        "margin_ema": margin_ema,
        "anchor_drift_ema": drift_ema,
        "margin_error": margin_error,
        "drift_ratio": drift_ratio,
        "pairwise_scale": pairwise_scale,
        "anchor_scale": anchor_scale,
        "lr_scale": lr_scale,
    }


def _response_logp(model: torch.nn.Module, sample: dict[str, torch.Tensor], *, device: torch.device) -> torch.Tensor:
    inputs = sample["inputs"].unsqueeze(0).to(device)
    targets = sample["targets"].unsqueeze(0).to(device)
    mask = sample["loss_mask"].to(device).reshape(-1).bool()
    logits = model(inputs).reshape(-1, model.vocab_size)
    logp = F.log_softmax(logits, dim=-1).gather(1, targets.reshape(-1, 1)).reshape(-1)
    if not bool(mask.any()):
        raise ValueError("viv_v33_pairwise_response_mask_empty")
    return logp[mask].mean()


def _masked_nll(logits: torch.Tensor, targets: torch.Tensor, masks: torch.Tensor) -> torch.Tensor:
    valid = masks.reshape(-1).bool()
    if not bool(valid.any()):
        raise ValueError("viv_v33_replay_mask_empty")
    return F.cross_entropy(logits.reshape(-1, logits.shape[-1])[valid], targets.reshape(-1)[valid])


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
        raise ValueError("viv_v33_steps_must_be_positive_multiple_of_250")
    if not math.isclose(learning_rate, LEARNING_RATE, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("viv_v33_learning_rate_is_fixed_for_this_objective")
    if output_dir.exists():
        raise FileExistsError(f"viv_v33_output_exists_refuse_overwrite:{output_dir}")
    authority = _validate_authority(authorize=authorize, steps=steps, learning_rate=learning_rate)
    tokenizer, input_manifest, replay_tensor_dir, source_evidence = _validate_sources()
    pair_samples = _load_pair_samples(tokenizer)
    train_inputs, train_targets, train_masks = base._load_split(
        replay_tensor_dir,
        "train",
        vocab_size=tokenizer.vocab_size,
        response_only_loss=True,
    )
    validation_inputs, validation_targets, validation_masks = base._load_split(
        replay_tensor_dir,
        "validation",
        vocab_size=tokenizer.vocab_size,
        response_only_loss=True,
    )
    if train_masks is None or validation_masks is None:
        raise ValueError("viv_v33_replay_response_masks_required")
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("viv_v33_cuda_requested_but_unavailable")
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
    batch_generator.manual_seed(seed + 330)
    history: list[dict[str, Any]] = []
    best_step = 0
    best_validation_nll = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    controller_state: dict[str, float | int | str] = {
        "schema_version": "viv_slm_v33_recursive_nudge_controller_v1",
        "alpha": CONTROLLER_ALPHA,
        "margin_ema": 0.0,
        "anchor_drift_ema": 0.0,
        "margin_error": CONTROLLER_TARGET_MARGIN,
        "drift_ratio": 0.0,
        "pairwise_scale": 1.0,
        "anchor_scale": 1.0,
        "lr_scale": 1.0,
    }
    model.train()

    for step in range(1, steps + 1):
        optimizer.zero_grad(set_to_none=True)
        pair_order = torch.randperm(len(pair_samples), generator=batch_generator).tolist()
        chosen_scores: list[torch.Tensor] = []
        rejected_scores: list[torch.Tensor] = []
        for index in pair_order:
            chosen_scores.append(_response_logp(model, pair_samples[index]["chosen_sample"], device=device))
            rejected_scores.append(_response_logp(model, pair_samples[index]["rejected_sample"], device=device))
        chosen_logp = torch.stack(chosen_scores)
        rejected_logp = torch.stack(rejected_scores)
        indices = torch.randint(0, train_inputs.shape[0], (batch_size,), generator=batch_generator)
        batch_inputs = train_inputs[indices].to(device)
        batch_targets = train_targets[indices].to(device)
        batch_masks = train_masks[indices].to(device)
        replay_logits = model(batch_inputs)
        replay_nll = _masked_nll(replay_logits, batch_targets, batch_masks)
        with torch.no_grad():
            reference_logits = reference(batch_inputs)
        anchor_drift = F.mse_loss(replay_logits.float(), reference_logits.float())
        controller_state = recursive_nudge_update(
            controller_state,
            observed_margin=float((chosen_logp.detach() - rejected_logp.detach()).mean()),
            observed_anchor_drift=float(anchor_drift.detach()),
        )
        effective_learning_rate = learning_rate * float(controller_state["lr_scale"])
        for parameter_group in optimizer.param_groups:
            parameter_group["lr"] = effective_learning_rate
        pair_values = objective_values(
            chosen_logp,
            rejected_logp,
            sft_weight=CHOSEN_SFT_WEIGHT,
            pairwise_weight=PAIRWISE_WEIGHT * float(controller_state["pairwise_scale"]),
            beta=PAIRWISE_BETA,
            margin=PAIRWISE_MARGIN,
        )
        effective_anchor_weight = REPLAY_ANCHOR_WEIGHT * float(controller_state["anchor_scale"])
        loss = pair_values["loss"].mean() + (REPLAY_SFT_WEIGHT * replay_nll) + (effective_anchor_weight * anchor_drift)
        loss.backward()
        grad_norm_before = float(torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=max_grad_norm))
        grad_norm_after = math.sqrt(
            sum(float(parameter.grad.detach().float().pow(2).sum()) for parameter in model.parameters() if parameter.grad is not None)
        )
        optimizer.step()

        if step % STEP_INCREMENT != 0:
            continue
        training_metrics = base._evaluate(model, train_inputs, train_targets, device=device, batch_size=eval_batch_size, loss_masks=train_masks)
        validation_metrics = base._evaluate(model, validation_inputs, validation_targets, device=device, batch_size=eval_batch_size, loss_masks=validation_masks)
        if float(validation_metrics["nll"]) < best_validation_nll:
            best_validation_nll = float(validation_metrics["nll"])
            best_step = step
            best_state = base._cpu_state_dict(model)
        record = {
            "step": step,
            "training": training_metrics,
            "validation": validation_metrics,
            "pairwise": {
                "chosen_mean_logp": float(chosen_logp.detach().mean()),
                "rejected_mean_logp": float(rejected_logp.detach().mean()),
                "mean_margin": float((chosen_logp.detach() - rejected_logp.detach()).mean()),
                "pairwise_loss": float(pair_values["pairwise_loss"].detach().mean()),
                "pair_correct": int(pair_values["pair_correct"].detach().sum()),
            },
            "replay_nll": float(replay_nll.detach()),
            "anchor_logit_mse": float(anchor_drift.detach()),
            "effective_learning_rate": effective_learning_rate,
            "effective_pairwise_weight": PAIRWISE_WEIGHT * float(controller_state["pairwise_scale"]),
            "effective_anchor_weight": effective_anchor_weight,
            "recursive_nudge_controller": dict(controller_state),
            "total_loss": float(loss.detach()),
            "grad_norm_before_clip": grad_norm_before,
            "grad_norm_after_clip": grad_norm_after,
            "best_validation_step": best_step,
            "best_validation_nll": best_validation_nll,
        }
        history.append(record)
        print(json.dumps(record, sort_keys=True))

    model.eval()
    termination_marker = str(input_manifest.get("termination_marker") or "<END>")
    generations = [
        {
            "prompt": "Viv:",
            "temperature": temperature,
            "top_k": top_k,
            "generated_token_count": sample_tokens,
            "text": base._sample(model, tokenizer, device=device, temperature=temperature, top_k=top_k, max_new_tokens=sample_tokens, seed=seed + 430 + index, stop_marker=termination_marker),
            "stop_marker": termination_marker,
        }
        for index, temperature in enumerate((0.0, 0.25, 0.5, 0.75, 1.0))
    ]
    checkpoint = {
        "schema_version": base.CHECKPOINT_SCHEMA,
        "model": base.MODEL_NAME,
        "weights_status": "trained",
        "training_steps": steps,
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
            "seed": seed,
            "device": str(device),
            "termination_marker": termination_marker,
            "response_only_loss": True,
            "initialization": "warm_start_v32_pairwise_identity_fresh_optimizer",
            "warm_start_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
            "v28_behavior_reference_checkpoint": str(V28_REFERENCE_CHECKPOINT).replace("\\", "/"),
            "objective": {
                "kind": "chosen_sft_plus_reference_free_pairwise_plus_v32_replay_anchor",
                "chosen_sft_weight": CHOSEN_SFT_WEIGHT,
                "pairwise_weight": PAIRWISE_WEIGHT,
                "pairwise_beta": PAIRWISE_BETA,
                "pairwise_margin": PAIRWISE_MARGIN,
                "replay_sft_weight": REPLAY_SFT_WEIGHT,
                "replay_anchor_weight": REPLAY_ANCHOR_WEIGHT,
                "rejected_is_sft_target": False,
                "adaptive_controller": dict(controller_state),
                "automatic_adjustment": "recursive_ema_margin_and_anchor_drift_bounded_nudge",
            },
        },
        "input_manifest": input_manifest,
        "source_evidence": source_evidence,
        "starting_sample": starting_sample,
        "training_history": history,
        "best_validation_step": best_step,
        "best_validation_nll": best_validation_nll,
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
    run_manifest = {
        "schema_version": base.SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED",
        "model": base.MODEL_NAME,
        "weights_status": "trained",
        "campaign_id": CAMPAIGN_ID,
        "training_steps": steps,
        "step_increment": STEP_INCREMENT,
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
        "prompt": "Viv:",
        "top_k": top_k,
        "sample_tokens": sample_tokens,
        "termination_marker": termination_marker,
        "response_only_loss": True,
        "initialization": "warm_start_v32_pairwise_identity_fresh_optimizer",
        "warm_start_checkpoint": str(PARENT_CHECKPOINT).replace("\\", "/"),
        "warm_start_checkpoint_sha256": PARENT_CHECKPOINT_SHA256,
        "v28_behavior_reference_checkpoint": str(V28_REFERENCE_CHECKPOINT).replace("\\", "/"),
        "v28_behavior_reference_checkpoint_sha256": V28_REFERENCE_CHECKPOINT_SHA256,
        "objective": checkpoint["training_config"]["objective"],
        "adaptive_controller_final": dict(controller_state),
        "initial_or_final": final,
        "best_validation_step": best_step,
        "best_validation_nll": best_validation_nll,
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
        "# Viv-SLM identity/personality pairwise refinement run\n\n"
        f"- Total optimizer steps: {steps}\n"
        f"- Increment: {STEP_INCREMENT}\n"
        f"- Vocabulary size: {tokenizer.vocab_size}\n"
        f"- Final validation NLL: {final.get('validation', {}).get('nll')}\n"
        f"- Best validation step: {best_step}\n"
        f"- Best validation NLL: {best_validation_nll}\n"
        "- Rejected responses used as SFT targets: false\n"
        "- World knowledge included: false\n"
        "- AIOS live mutation: false\n"
        "- Promotion/deployment: closed\n",
        encoding="utf-8",
        newline="\n",
    )
    _json_write(
        output_dir / "AUTHORIZATION.json",
        {
            "schema_version": "viv_slm_v33_training_authorization_v1",
            "campaign_id": CAMPAIGN_ID,
            "authorized_utc": authority["task_updated_utc"],
            "input_manifest_sha256": source_evidence["input_manifest_sha256"],
            "pairwise_rows_sha256": source_evidence["pairwise_rows_sha256"],
            "parent_checkpoint": authority["parent_checkpoint"],
            "parent_checkpoint_sha256": authority["parent_checkpoint_sha256"],
            "steps": steps,
            "step_increment": STEP_INCREMENT,
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
    print(json.dumps({"status": "VIV_SLM_V33_PAIRWISE_IDENTITY_TRAINING_COMPLETE", "campaign_id": CAMPAIGN_ID, "checkpoint": result["checkpoint"], "training_steps": result["training_steps"], "best_validation_nll": result["best_validation_nll"], "learning_rate": LEARNING_RATE, "training_authorized": result["training_authorized"], "run_authorized": result["run_authorized"], "promotion_authorized": result["promotion_authorized"], "deployment_changed": result["deployment_changed"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
