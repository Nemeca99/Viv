#!/usr/bin/env python3
"""Train the Part 6 transformer for the bounded Part 7 experiment."""
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

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from dataset import load_tensor_shard, tensor_shards  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

DEFAULT_VOCAB = HERE / "artifacts" / "run_500_steps" / "vocab" / "VOCAB.json"
DEFAULT_DATASET = HERE / "artifacts" / "run_500_steps" / "tensor_dataset"
DEFAULT_RANDOM_INIT = HERE / "artifacts" / "part6_transformer_random_init" / "random_init.pt"
DEFAULT_OUTPUT = HERE / "artifacts" / "part7_training_1500_steps"


def _json_write(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_split(
    dataset_dir: Path | str,
    split: str,
    *,
    vocab_size: int,
) -> tuple[torch.Tensor, torch.Tensor]:
    inputs: list[torch.Tensor] = []
    targets: list[torch.Tensor] = []
    for path in tensor_shards(dataset_dir, split):
        split_inputs, split_targets = load_tensor_shard(path, vocab_size=vocab_size)
        inputs.append(split_inputs)
        targets.append(split_targets)
    return torch.cat(inputs, dim=0), torch.cat(targets, dim=0)


def _evaluate(
    model: TransformerLanguageModel,
    inputs: torch.Tensor,
    targets: torch.Tensor,
    *,
    device: torch.device,
    batch_size: int,
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


def _sample_text(
    model: TransformerLanguageModel,
    tokenizer: CharacterTokenizer,
    prompt: str,
    *,
    temperature: float,
    top_k: int,
    max_new_tokens: int,
    device: torch.device,
    generator_seed: int,
) -> str:
    prompt_ids = torch.tensor(
        [tokenizer.encode(prompt)],
        dtype=torch.long,
        device=device,
    )
    generator = torch.Generator(device=device)
    generator.manual_seed(generator_seed)
    output = model.generate(
        prompt_ids,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_k=top_k,
        generator=generator,
    )
    return tokenizer.decode(output[0].detach().cpu().tolist())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocab", default=str(DEFAULT_VOCAB))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--random-init", default=str(DEFAULT_RANDOM_INIT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--steps", type=int, default=1500)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--eval-batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.0003)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--prompt", default="Viv:")
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--sample-tokens", type=int, default=160)
    parser.add_argument(
        "--temperatures",
        type=float,
        nargs="+",
        default=[0.0, 0.25, 0.5, 0.75, 1.0],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.steps != 1500:
        raise ValueError("part7_requires_exactly_1500_steps")
    if args.batch_size <= 0 or args.eval_batch_size <= 0:
        raise ValueError("part7_batch_sizes_must_be_positive")
    if args.learning_rate <= 0 or args.max_grad_norm <= 0:
        raise ValueError("part7_optimizer_parameters_must_be_positive")
    if args.top_k <= 0 or args.sample_tokens < 0:
        raise ValueError("part7_generation_parameters_invalid")
    if any(temperature < 0 for temperature in args.temperatures):
        raise ValueError("part7_temperature_must_not_be_negative")

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    starting_sample_path = output / "starting_sample.txt"
    history_path = output / "training_history.json"
    generations_path = output / "generation_comparison.json"
    checkpoint_path = output / "checkpoint.pt"
    manifest_path = output / "RUN_MANIFEST.json"
    report_path = output / "RUN_REPORT.md"
    for path in (
        starting_sample_path,
        history_path,
        generations_path,
        checkpoint_path,
        manifest_path,
        report_path,
    ):
        if path.exists():
            raise FileExistsError(f"part7_output_exists_refuse_overwrite:{path}")

    tokenizer = CharacterTokenizer.from_manifest(args.vocab)
    random_init = torch.load(args.random_init, map_location="cpu", weights_only=True)
    if not isinstance(random_init, dict):
        raise ValueError("part6_random_init_checkpoint_requires_object")
    if random_init.get("weights_status") != "random_initialization":
        raise ValueError("part6_random_init_checkpoint_not_random")
    if random_init.get("training_steps") != 0:
        raise ValueError("part6_random_init_checkpoint_already_trained")
    if random_init.get("vocab_sha256") != tokenizer.vocab_sha256:
        raise ValueError("part7_vocab_hash_mismatch")
    config = random_init.get("config")
    if not isinstance(config, dict):
        raise ValueError("part6_random_init_config_missing")

    train_inputs, train_targets = _load_split(
        args.dataset,
        "train",
        vocab_size=tokenizer.vocab_size,
    )
    validation_inputs, validation_targets = _load_split(
        args.dataset,
        "validation",
        vocab_size=tokenizer.vocab_size,
    )
    device = torch.device(args.device)
    torch.manual_seed(args.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)
    model = TransformerLanguageModel(
        tokenizer.vocab_size,
        context_length=int(config["context_length"]),
        embedding_width=int(config["embedding_width"]),
        num_heads=int(config["num_heads"]),
        head_size=int(config["head_size"]),
        num_layers=int(config["num_layers"]),
        dropout=float(config["dropout"]),
    )
    model.load_state_dict(random_init["model_state_dict"])
    model.to(device)
    model.eval()

    baseline = _sample_text(
        model,
        tokenizer,
        args.prompt,
        temperature=0.0,
        top_k=args.top_k,
        max_new_tokens=args.sample_tokens,
        device=device,
        generator_seed=args.seed + 100,
    )
    starting_sample_path.write_text(
        f"source=random_init.pt\n"
        f"prompt={args.prompt!r}\n"
        f"temperature=0.0\n"
        f"top_k={args.top_k}\n"
        f"generated_token_count={args.sample_tokens}\n"
        f"text={baseline!r}\n",
        encoding="utf-8",
        newline="\n",
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    batch_generator = torch.Generator(device="cpu")
    batch_generator.manual_seed(args.seed + 200)
    history: list[dict[str, Any]] = []

    initial_train = _evaluate(
        model,
        train_inputs,
        train_targets,
        device=device,
        batch_size=args.eval_batch_size,
    )
    initial_validation = _evaluate(
        model,
        validation_inputs,
        validation_targets,
        device=device,
        batch_size=args.eval_batch_size,
    )
    history.append(
        {
            "step": 0,
            "training": initial_train,
            "validation": initial_validation,
            "grad_norm_before_clip": None,
            "grad_norm_after_clip": None,
        }
    )
    print(json.dumps(history[-1], sort_keys=True))

    model.train()
    for step in range(1, args.steps + 1):
        indices = torch.randint(
            0,
            train_inputs.shape[0],
            (args.batch_size,),
            generator=batch_generator,
        )
        batch_inputs = train_inputs[indices].to(device)
        batch_targets = train_targets[indices].to(device)
        optimizer.zero_grad(set_to_none=True)
        logits = model(batch_inputs)
        loss, _ = model.loss_and_accuracy(logits, batch_targets)
        loss.backward()
        grad_norm_before = float(
            torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                max_norm=args.max_grad_norm,
            )
        )
        optimizer.step()
        if step % 250 == 0:
            training_metrics = _evaluate(
                model,
                train_inputs,
                train_targets,
                device=device,
                batch_size=args.eval_batch_size,
            )
            validation_metrics = _evaluate(
                model,
                validation_inputs,
                validation_targets,
                device=device,
                batch_size=args.eval_batch_size,
            )
            grad_norm_after = 0.0
            for parameter in model.parameters():
                if parameter.grad is not None:
                    grad_norm_after += float(parameter.grad.detach().float().pow(2).sum())
            grad_norm_after = math.sqrt(grad_norm_after)
            record = {
                "step": step,
                "training": training_metrics,
                "validation": validation_metrics,
                "grad_norm_before_clip": grad_norm_before,
                "grad_norm_after_clip": grad_norm_after,
            }
            history.append(record)
            print(json.dumps(record, sort_keys=True))

    model.eval()
    generations: list[dict[str, Any]] = []
    for index, temperature in enumerate(args.temperatures):
        text = _sample_text(
            model,
            tokenizer,
            args.prompt,
            temperature=temperature,
            top_k=args.top_k,
            max_new_tokens=args.sample_tokens,
            device=device,
            generator_seed=args.seed + 300 + index,
        )
        generations.append(
            {
                "temperature": temperature,
                "top_k": args.top_k,
                "prompt": args.prompt,
                "generated_token_count": args.sample_tokens,
                "text": text,
            }
        )
    _json_write(generations_path, {"schema_version": "uml_part7_generation_comparison_v1", "samples": generations})
    _json_write(history_path, {"schema_version": "uml_part7_training_history_v1", "measurements": history})

    checkpoint = {
        "schema_version": "uml_part7_trained_transformer_checkpoint_v1",
        "model": "four_block_four_head_transformer",
        "weights_status": "trained",
        "training_steps": args.steps,
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "tokenizer": tokenizer.manifest(),
        "model_config": config,
        "training_config": {
            "batch_size": args.batch_size,
            "eval_batch_size": args.eval_batch_size,
            "learning_rate": args.learning_rate,
            "optimizer": "AdamW",
            "max_grad_norm": args.max_grad_norm,
            "evaluation_interval": 250,
            "seed": args.seed,
            "device": str(device),
        },
        "starting_sample": baseline,
        "training_history": history,
        "generation_comparison": generations,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
    }
    torch.save(checkpoint, checkpoint_path)
    final = history[-1]
    manifest = {
        "schema_version": "uml_part7_training_run_v1",
        "status": "COMPLETE",
        "model": "four_block_four_head_transformer",
        "weights_status": "trained",
        "training_steps": args.steps,
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "random_init_checkpoint": str(Path(args.random_init).resolve()).replace("\\", "/"),
        "random_init_sha256": _file_sha256(Path(args.random_init)),
        "learning_rate": args.learning_rate,
        "optimizer": "AdamW",
        "max_grad_norm": args.max_grad_norm,
        "evaluation_interval": 250,
        "batch_size": args.batch_size,
        "eval_batch_size": args.eval_batch_size,
        "device": str(device),
        "prompt": args.prompt,
        "top_k": args.top_k,
        "temperatures": args.temperatures,
        "starting_sample_sha256": _file_sha256(starting_sample_path),
        "history_sha256": _file_sha256(history_path),
        "generations_sha256": _file_sha256(generations_path),
        "checkpoint_sha256": _file_sha256(checkpoint_path),
        "initial": history[0],
        "final": final,
        "aios_live_mutation": False,
        "next_step": "Part 8",
    }
    _json_write(manifest_path, manifest)
    report_path.write_text(
        "# Part 7 run report\n\n"
        f"- Steps: `{args.steps}`\n"
        f"- Optimizer: `AdamW`\n"
        f"- Learning rate: `{args.learning_rate}`\n"
        f"- Gradient clip max norm: `{args.max_grad_norm}`\n"
        f"- Evaluation interval: every `{250}` steps\n"
        f"- Device: `{device}`\n"
        f"- Initial training NLL: `{history[0]['training']['nll']:.6f}`\n"
        f"- Final training NLL: `{final['training']['nll']:.6f}`\n"
        f"- Initial validation NLL: `{history[0]['validation']['nll']:.6f}`\n"
        f"- Final validation NLL: `{final['validation']['nll']:.6f}`\n"
        f"- Temperature comparison: `{args.temperatures}` with top-k `{args.top_k}`\n"
        "- Starting sample saved before optimizer creation: `true`\n"
        "- AIOS live mutation: `false`\n\n"
        "The starting and generated samples are diagnostics; they are not claims of language competence.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
