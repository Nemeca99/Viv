#!/usr/bin/env python3
"""Train Viv-SLM identity/personality in bounded 250-step increments."""
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
INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v1" / "inputs"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v1" / "runs" / "identity_personality_steps_1000"
MODEL_EXPERIMENT_ROOT = VIV_ROOT / "models" / "uml_bigram_part3"
if str(MODEL_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_EXPERIMENT_ROOT))

from dataset import load_tensor_shard, tensor_shards  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

MODEL_NAME = "Viv-SLM"
SCHEMA_VERSION = "viv_slm_identity_personality_training_v1"
CHECKPOINT_SCHEMA = "viv_slm_identity_personality_checkpoint_v1"
STEP_INCREMENT = 250
MASKED_TENSOR_SCHEMAS = {
    "viv_slm_response_only_tensor_dataset_v1",
    "viv_slm_dialogue_aligned_tensor_dataset_v1",
    "viv_slm_dialogue_aligned_chunked_tensor_dataset_v2",
    "viv_slm_route_conditioned_chunked_tensor_dataset_v1",
    "viv_slm_packed_route_conditioned_response_only_tensor_dataset_v1",
}
MODEL_CONFIG = {
    "context_length": 128,
    "embedding_width": 128,
    "num_heads": 4,
    "head_size": 32,
    "num_layers": 4,
    "dropout": 0.1,
}


def _json_write(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_split(
    dataset_dir: Path,
    split: str,
    *,
    vocab_size: int,
    response_only_loss: bool = False,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor | None]:
    inputs: list[torch.Tensor] = []
    targets: list[torch.Tensor] = []
    masks: list[torch.Tensor] = []
    if response_only_loss:
        for path in sorted((dataset_dir / split).glob("shard_*.pt")):
            payload = torch.load(path, map_location="cpu", weights_only=True)
            if not isinstance(payload, dict) or payload.get("schema_version") not in MASKED_TENSOR_SCHEMAS:
                raise ValueError(f"viv_slm_masked_tensor_schema_mismatch:{path}")
            split_inputs = payload.get("inputs")
            split_targets = payload.get("targets")
            split_masks = payload.get("loss_mask")
            if not all(isinstance(value, torch.Tensor) for value in (split_inputs, split_targets, split_masks)):
                raise ValueError(f"viv_slm_masked_tensor_missing:{path}")
            if split_inputs.shape != split_targets.shape or split_masks.shape != split_inputs.shape:
                raise ValueError(f"viv_slm_masked_tensor_shape_mismatch:{path}")
            if split_inputs.ndim != 2 or split_masks.dtype != torch.bool:
                raise ValueError(f"viv_slm_masked_tensor_dtype_mismatch:{path}")
            if split_inputs.numel() and (
                int(split_inputs.min()) < 0
                or int(split_inputs.max()) >= vocab_size
                or int(split_targets.min()) < 0
                or int(split_targets.max()) >= vocab_size
            ):
                raise ValueError(f"viv_slm_masked_tensor_token_range_mismatch:{path}")
            inputs.append(split_inputs.to(dtype=torch.long))
            targets.append(split_targets.to(dtype=torch.long))
            masks.append(split_masks)
        if not inputs:
            raise FileNotFoundError(f"viv_slm_masked_tensor_shards_missing:{dataset_dir / split}")
        return torch.cat(inputs, dim=0), torch.cat(targets, dim=0), torch.cat(masks, dim=0)
    for path in tensor_shards(dataset_dir, split):
        split_inputs, split_targets = load_tensor_shard(path, vocab_size=vocab_size)
        inputs.append(split_inputs)
        targets.append(split_targets)
    return torch.cat(inputs, dim=0), torch.cat(targets, dim=0), None


def _evaluate(
    model: TransformerLanguageModel,
    inputs: torch.Tensor,
    targets: torch.Tensor,
    *,
    device: torch.device,
    batch_size: int,
    loss_masks: torch.Tensor | None = None,
) -> dict[str, float | int]:
    was_training = model.training
    model.eval()
    total_nll = 0.0
    total_correct = 0
    total_tokens = 0
    with torch.no_grad():
        for start in range(0, inputs.shape[0], batch_size):
            batch_inputs = inputs[start : start + batch_size].to(device)
            batch_targets = targets[start : start + batch_size].to(device)
            logits = model(batch_inputs)
            flat_logits = logits.reshape(-1, model.vocab_size)
            flat_targets = batch_targets.reshape(-1)
            if loss_masks is None:
                valid = None
            else:
                valid = loss_masks[start : start + batch_size].to(device).reshape(-1).bool()
                if not bool(valid.any()):
                    continue
                flat_logits = flat_logits[valid]
                flat_targets = flat_targets[valid]
            total_nll += float(
                F.cross_entropy(flat_logits, flat_targets, reduction="sum")
            )
            total_correct += int((flat_logits.argmax(dim=-1) == flat_targets).sum())
            total_tokens += int(flat_targets.numel())
    if was_training:
        model.train()
    nll = total_nll / total_tokens
    return {
        "examples": int(inputs.shape[0]),
        "tokens": total_tokens,
        "nll": nll,
        "perplexity": math.exp(nll),
        "token_accuracy": total_correct / total_tokens,
    }


def _cpu_state_dict(model: TransformerLanguageModel) -> dict[str, torch.Tensor]:
    return {
        key: value.detach().cpu().clone()
        for key, value in model.state_dict().items()
    }


def _sample(
    model: TransformerLanguageModel,
    tokenizer: CharacterTokenizer,
    *,
    device: torch.device,
    temperature: float,
    top_k: int,
    max_new_tokens: int,
    seed: int,
    stop_marker: str | None = None,
) -> str:
    prompt = "Viv:"
    prompt_ids = tokenizer.encode(prompt)
    ids = torch.tensor([prompt_ids], dtype=torch.long, device=device)
    generator = torch.Generator(device=device)
    generator.manual_seed(seed)
    with torch.no_grad():
        output = model.generate(
            ids,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_k=top_k,
            generator=generator,
        )
    text = tokenizer.decode(output[0].detach().cpu().tolist())
    if stop_marker:
        marker_index = text.find(stop_marker)
        if marker_index >= 0:
            return text[:marker_index].rstrip()
    return text


def _make_model(vocab_size: int, *, device: torch.device) -> TransformerLanguageModel:
    model = TransformerLanguageModel(vocab_size, **MODEL_CONFIG)
    return model.to(device)


def _validate_input(input_root: Path) -> tuple[CharacterTokenizer, dict[str, Any], Path]:
    vocab_path = input_root / "VOCAB.json"
    tensor_dir = input_root / "tensor_dataset"
    input_manifest_path = input_root / "INPUT_MANIFEST.json"
    if not vocab_path.is_file() or not tensor_dir.is_dir() or not input_manifest_path.is_file():
        raise FileNotFoundError(f"viv_slm_training_inputs_missing:{input_root}")
    input_manifest = json.loads(input_manifest_path.read_text(encoding="utf-8"))
    if input_manifest.get("world_knowledge_included") is not False:
        raise ValueError("viv_slm_training_input_world_knowledge_policy_violation")
    if input_manifest.get("training_authorized") is not False:
        raise ValueError("viv_slm_training_input_authority_flag_changed")
    tokenizer = CharacterTokenizer.from_manifest(vocab_path)
    if tokenizer.vocab_size != 96:
        raise ValueError("viv_slm_expected_vocab_size_96")
    termination_marker = input_manifest.get("termination_marker")
    if termination_marker is not None:
        if not isinstance(termination_marker, str) or not termination_marker:
            raise ValueError("viv_slm_termination_marker_invalid")
        tokenizer.encode(termination_marker)
    return tokenizer, input_manifest, tensor_dir


def _load_resume(
    path: Path,
    *,
    tokenizer: CharacterTokenizer,
    model: TransformerLanguageModel,
    optimizer: torch.optim.Optimizer,
    response_only_loss: bool,
) -> tuple[int, list[dict[str, Any]], str, dict[str, Any] | None]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != CHECKPOINT_SCHEMA:
        raise ValueError("viv_slm_resume_checkpoint_schema_mismatch")
    if checkpoint.get("vocab_sha256") != tokenizer.vocab_sha256:
        raise ValueError("viv_slm_resume_vocab_hash_mismatch")
    model_config = checkpoint.get("model_config")
    if model_config != MODEL_CONFIG:
        raise ValueError("viv_slm_resume_model_config_mismatch")
    training_config = checkpoint.get("training_config")
    recorded_response_only = bool(training_config.get("response_only_loss")) if isinstance(training_config, Mapping) else False
    if recorded_response_only != response_only_loss:
        raise ValueError("viv_slm_resume_loss_mode_mismatch")
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
    start_step = int(checkpoint.get("training_steps") or 0)
    if start_step < 0 or start_step % STEP_INCREMENT != 0:
        raise ValueError("viv_slm_resume_step_boundary_invalid")
    history = checkpoint.get("training_history")
    if not isinstance(history, list):
        raise ValueError("viv_slm_resume_history_missing")
    starting_sample = str(checkpoint.get("starting_sample") or "")
    best_step = checkpoint.get("best_validation_step")
    best_state = checkpoint.get("best_model_state_dict")
    if best_state is not None and not isinstance(best_state, Mapping):
        raise ValueError("viv_slm_resume_best_state_invalid")
    return start_step, list(history), starting_sample, dict(best_state) if best_state else None


def _load_warm_start(
    path: Path,
    *,
    tokenizer: CharacterTokenizer,
    model: TransformerLanguageModel,
) -> str:
    """Load only model weights so a new loss objective starts a fresh optimizer lane."""
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != CHECKPOINT_SCHEMA:
        raise ValueError("viv_slm_warm_start_checkpoint_schema_mismatch")
    if checkpoint.get("vocab_sha256") != tokenizer.vocab_sha256:
        raise ValueError("viv_slm_warm_start_vocab_hash_mismatch")
    if checkpoint.get("model_config") != MODEL_CONFIG:
        raise ValueError("viv_slm_warm_start_model_config_mismatch")
    model_state = checkpoint.get("model_state_dict")
    if not isinstance(model_state, Mapping):
        raise ValueError("viv_slm_warm_start_model_state_missing")
    model.load_state_dict(model_state, strict=True)
    return str(checkpoint.get("starting_sample") or "")


def train(
    *,
    input_root: Path = INPUT_ROOT,
    output_dir: Path = DEFAULT_OUTPUT,
    steps: int = 1000,
    resume: Path | None = None,
    warm_start: Path | None = None,
    batch_size: int = 64,
    eval_batch_size: int = 64,
    learning_rate: float = 0.0003,
    max_grad_norm: float = 1.0,
    seed: int = 42,
    device_name: str = "cuda",
    sample_tokens: int = 160,
    top_k: int = 40,
) -> dict[str, Any]:
    if steps <= 0 or steps % STEP_INCREMENT != 0:
        raise ValueError("viv_slm_steps_must_be_positive_multiple_of_250")
    if batch_size <= 0 or eval_batch_size <= 0:
        raise ValueError("viv_slm_batch_size_invalid")
    if learning_rate <= 0 or max_grad_norm <= 0:
        raise ValueError("viv_slm_optimizer_parameter_invalid")
    if sample_tokens < 0 or top_k <= 0:
        raise ValueError("viv_slm_generation_parameter_invalid")
    if resume is not None and warm_start is not None:
        raise ValueError("viv_slm_resume_and_warm_start_are_mutually_exclusive")
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("viv_slm_cuda_requested_but_unavailable")
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_training_output_exists_refuse_overwrite:{output_dir}")
    output_dir.mkdir(parents=True)

    tokenizer, input_manifest, tensor_dir = _validate_input(input_root)
    termination_marker = input_manifest.get("termination_marker")
    response_only_loss = input_manifest.get("response_only_loss", False)
    if not isinstance(response_only_loss, bool):
        raise ValueError("viv_slm_response_only_loss_flag_invalid")
    train_inputs, train_targets, train_loss_masks = _load_split(
        tensor_dir,
        "train",
        vocab_size=tokenizer.vocab_size,
        response_only_loss=response_only_loss,
    )
    validation_inputs, validation_targets, validation_loss_masks = _load_split(
        tensor_dir,
        "validation",
        vocab_size=tokenizer.vocab_size,
        response_only_loss=response_only_loss,
    )
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
    model = _make_model(tokenizer.vocab_size, device=device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    start_step = 0
    history: list[dict[str, Any]] = []
    starting_sample = ""
    best_step = 0
    best_validation_nll = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    initialization = "random_initialization"

    if resume is None and warm_start is None:
        model.eval()
        starting_sample = _sample(
            model,
            tokenizer,
            device=device,
            temperature=0.0,
            top_k=top_k,
            max_new_tokens=sample_tokens,
            seed=seed + 100,
            stop_marker=termination_marker,
        )
        torch.save(
            {
                "schema_version": "viv_slm_identity_personality_random_init_v1",
                "model": MODEL_NAME,
                "weights_status": "random_initialization",
                "training_steps": 0,
                "vocab_size": tokenizer.vocab_size,
                "vocab_sha256": tokenizer.vocab_sha256,
                "model_config": MODEL_CONFIG,
                "seed": seed,
                "aios_live_mutation": False,
            },
            output_dir / "random_init.pt",
        )
        model.train()
    elif warm_start is not None:
        starting_sample = _load_warm_start(
            Path(warm_start),
            tokenizer=tokenizer,
            model=model,
        )
        initialization = "warm_start_model_weights_fresh_optimizer"
        model.train()
    else:
        start_step, history, starting_sample, best_state = _load_resume(
            Path(resume),
            tokenizer=tokenizer,
            model=model,
            optimizer=optimizer,
            response_only_loss=response_only_loss,
        )
        best_step = int(history[-1].get("best_validation_step") or start_step) if history else start_step
        if history:
            best_validation_nll = min(
                float(item["validation"]["nll"])
                for item in history
                if isinstance(item, Mapping) and isinstance(item.get("validation"), Mapping)
            )
        initialization = "resume_optimizer_state"
        model.train()

    batch_generator = torch.Generator(device="cpu")
    batch_generator.manual_seed(seed + 200 + start_step)
    target_step = start_step + steps
    for step in range(start_step + 1, target_step + 1):
        indices = torch.randint(
            0,
            train_inputs.shape[0],
            (batch_size,),
            generator=batch_generator,
        )
        batch_inputs = train_inputs[indices].to(device)
        batch_targets = train_targets[indices].to(device)
        batch_loss_masks = train_loss_masks[indices].to(device) if train_loss_masks is not None else None
        optimizer.zero_grad(set_to_none=True)
        logits = model(batch_inputs)
        if batch_loss_masks is None:
            loss, _ = model.loss_and_accuracy(logits, batch_targets)
        else:
            valid = batch_loss_masks.reshape(-1).bool()
            if not bool(valid.any()):
                raise ValueError("viv_slm_batch_contains_no_response_targets")
            loss = F.cross_entropy(
                logits.reshape(-1, model.vocab_size)[valid],
                batch_targets.reshape(-1)[valid],
            )
        loss.backward()
        grad_norm_before = float(
            torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                max_norm=max_grad_norm,
            )
        )
        grad_norm_after = math.sqrt(
            sum(
                float(parameter.grad.detach().float().pow(2).sum())
                for parameter in model.parameters()
                if parameter.grad is not None
            )
        )
        optimizer.step()

        absolute_step = step
        if absolute_step % STEP_INCREMENT != 0:
            continue
        training_metrics = _evaluate(
            model,
            train_inputs,
            train_targets,
            device=device,
            batch_size=eval_batch_size,
            loss_masks=train_loss_masks,
        )
        validation_metrics = _evaluate(
            model,
            validation_inputs,
            validation_targets,
            device=device,
            batch_size=eval_batch_size,
            loss_masks=validation_loss_masks,
        )
        if float(validation_metrics["nll"]) < best_validation_nll:
            best_validation_nll = float(validation_metrics["nll"])
            best_step = absolute_step
            best_state = _cpu_state_dict(model)
        record = {
            "step": absolute_step,
            "training": training_metrics,
            "validation": validation_metrics,
            "grad_norm_before_clip": grad_norm_before,
            "grad_norm_after_clip": grad_norm_after,
            "best_validation_step": best_step,
            "best_validation_nll": best_validation_nll,
        }
        history.append(record)
        print(json.dumps(record, sort_keys=True))

    model.eval()
    generations = []
    for index, temperature in enumerate((0.0, 0.25, 0.5, 0.75, 1.0)):
        generations.append(
            {
                "prompt": "Viv:",
                "temperature": temperature,
                "top_k": top_k,
                "generated_token_count": sample_tokens,
                "text": _sample(
                    model,
                    tokenizer,
                    device=device,
                    temperature=temperature,
                    top_k=top_k,
                    max_new_tokens=sample_tokens,
                    seed=seed + 300 + start_step + index,
                    stop_marker=termination_marker,
                ),
                "stop_marker": termination_marker,
            }
        )
    checkpoint = {
        "schema_version": CHECKPOINT_SCHEMA,
        "model": MODEL_NAME,
        "weights_status": "trained",
        "training_steps": target_step,
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "model_config": MODEL_CONFIG,
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
            "response_only_loss": response_only_loss,
            "initialization": initialization,
            "warm_start_checkpoint": str(warm_start).replace("\\", "/") if warm_start is not None else None,
            "resume_checkpoint": str(resume).replace("\\", "/") if resume is not None else None,
        },
        "input_manifest": input_manifest,
        "starting_sample": starting_sample,
        "training_history": history,
        "best_validation_step": best_step,
        "best_validation_nll": best_validation_nll,
        "best_model_state_dict": best_state,
        "generation_comparison": generations,
        "model_state_dict": _cpu_state_dict(model),
        "optimizer_state_dict": optimizer.state_dict(),
        "aios_live_mutation": False,
        "knowledge_policy": "external_cpu_retrieval_only",
    }
    checkpoint_path = output_dir / "checkpoint.pt"
    torch.save(checkpoint, checkpoint_path)
    final = history[-1] if history else {}
    run_manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED",
        "model": MODEL_NAME,
        "weights_status": "trained",
        "training_steps": target_step,
        "step_increment": STEP_INCREMENT,
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "input_manifest": str(input_root / "INPUT_MANIFEST.json").replace("\\", "/"),
        "input_manifest_sha256": _sha256(input_root / "INPUT_MANIFEST.json"),
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
        "response_only_loss": response_only_loss,
        "initial_sample": (
            str(output_dir / "random_init.pt").replace("\\", "/")
            if initialization == "random_initialization"
            else "inherited_from_warm_start"
            if warm_start is not None
            else "inherited_from_resume"
        ),
        "initialization": initialization,
        "warm_start_checkpoint": str(warm_start).replace("\\", "/") if warm_start is not None else None,
        "resume_checkpoint": str(resume).replace("\\", "/") if resume is not None else None,
        "initial_sample_text": starting_sample,
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
        "next_step": "inspect_generation_and_extend_only_in_another_250_step_run",
    }
    _json_write(output_dir / "generation_comparison.json", {"samples": generations})
    _json_write(output_dir / "training_history.json", {"measurements": history})
    _json_write(output_dir / "RUN_MANIFEST.json", run_manifest)
    (output_dir / "RUN_REPORT.md").write_text(
        "# Viv-SLM identity/personality training run\n\n"
        f"- Total optimizer steps: {target_step}\n"
        f"- Increment: {STEP_INCREMENT}\n"
        f"- Vocabulary size: {tokenizer.vocab_size}\n"
        f"- Final validation NLL: {final.get('validation', {}).get('nll')}\n"
        f"- Best validation step: {best_step}\n"
        f"- Best validation NLL: {best_validation_nll}\n"
        "- World knowledge included: false\n"
        "- AIOS live mutation: false\n"
        "- Promotion/deployment: closed\n",
        encoding="utf-8",
        newline="\n",
    )
    return run_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=INPUT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--resume", type=Path, default=None)
    parser.add_argument("--warm-start", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--eval-batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.0003)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--sample-tokens", type=int, default=160)
    parser.add_argument("--top-k", type=int, default=40)
    args = parser.parse_args(argv)
    result = train(
        input_root=args.input_root,
        output_dir=args.output_dir,
        steps=args.steps,
        resume=args.resume,
        warm_start=args.warm_start,
        batch_size=args.batch_size,
        eval_batch_size=args.eval_batch_size,
        learning_rate=args.learning_rate,
        max_grad_norm=args.max_grad_norm,
        seed=args.seed,
        device_name=args.device,
        sample_tokens=args.sample_tokens,
        top_k=args.top_k,
    )
    print(
        json.dumps(
            {
                "status": "VIV_SLM_TRAINING_PASS",
                "run": result["checkpoint"],
                "training_steps": result["training_steps"],
                "best_validation_step": result["best_validation_step"],
                "best_validation_nll": result["best_validation_nll"],
                "world_knowledge_included": result["world_knowledge_included"],
                "aios_live_mutation": result["aios_live_mutation"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
