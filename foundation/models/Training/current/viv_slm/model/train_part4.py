#!/usr/bin/env python3
"""Train the isolated Part 4 causal context model for 500 steps."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from typing import Any

import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from context import ContextLanguageModel  # noqa: E402
from dataset import first_batch  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

DEFAULT_VOCAB = HERE / "artifacts" / "run_500_steps" / "vocab" / "VOCAB.json"
DEFAULT_DATASET = HERE / "artifacts" / "run_500_steps" / "tensor_dataset"
DEFAULT_OUTPUT = HERE / "artifacts" / "part4_context_500_steps"


def _json_write(path: Path, value: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _measure(
    model: ContextLanguageModel,
    inputs: torch.Tensor,
    targets: torch.Tensor,
) -> dict[str, float]:
    with torch.no_grad():
        logits = model(inputs)
        loss, accuracy = model.loss_and_accuracy(logits, targets)
    nll = float(loss)
    return {
        "nll": nll,
        "perplexity": math.exp(nll),
        "token_accuracy": float(accuracy),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocab", default=str(DEFAULT_VOCAB))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--context-length", type=int, default=128)
    parser.add_argument("--embedding-width", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--sample-tokens", type=int, default=160)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.steps != 500:
        raise ValueError("part4_requires_exactly_500_steps")
    if min(args.batch_size, args.context_length, args.embedding_width, args.sample_tokens) < 0:
        raise ValueError("invalid_training_parameter")
    if args.batch_size == 0 or args.context_length == 0 or args.embedding_width == 0:
        raise ValueError("training_dimensions_must_be_positive")

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "checkpoint.pt"
    metrics_path = output / "metrics.json"
    sample_path = output / "generated_sample.txt"
    run_manifest_path = output / "RUN_MANIFEST.json"
    for path in (checkpoint_path, metrics_path, sample_path, run_manifest_path):
        if path.exists():
            raise FileExistsError(f"training_output_exists_refuse_overwrite:{path}")

    tokenizer = CharacterTokenizer.from_manifest(args.vocab)
    inputs, targets = first_batch(
        args.dataset,
        vocab_size=tokenizer.vocab_size,
        batch_size=args.batch_size,
    )
    if int(inputs.shape[1]) != args.context_length:
        raise ValueError(
            f"dataset_context_length_mismatch:{int(inputs.shape[1])}:{args.context_length}"
        )
    device = torch.device(args.device)
    inputs = inputs.to(device)
    targets = targets.to(device)
    torch.manual_seed(args.seed)
    model = ContextLanguageModel(
        tokenizer.vocab_size,
        context_length=args.context_length,
        embedding_width=args.embedding_width,
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=0.0,
    )

    checkpoints = {0, 1, 100, 200, 300, 400, 500}
    measured: list[dict[str, Any]] = []
    measured.append({"step": 0, **_measure(model, inputs, targets)})

    model.train()
    for step in range(1, args.steps + 1):
        optimizer.zero_grad(set_to_none=True)
        logits = model(inputs)
        loss, _ = model.loss_and_accuracy(logits, targets)
        loss.backward()
        optimizer.step()
        if step in checkpoints:
            measured.append({"step": step, **_measure(model, inputs, targets)})

    final = measured[-1]
    model.eval()
    prompt = "Viv:"
    try:
        prompt_ids = torch.tensor([tokenizer.encode(prompt)], dtype=torch.long, device=device)
    except ValueError:
        prompt = tokenizer.vocab[0]
        prompt_ids = torch.tensor([tokenizer.encode(prompt)], dtype=torch.long, device=device)
    generator = torch.Generator(device=device)
    generator.manual_seed(args.seed + 1)
    generated_ids = model.generate(
        prompt_ids,
        max_new_tokens=args.sample_tokens,
        temperature=1.0,
        generator=generator,
    )
    generated_text = tokenizer.decode(generated_ids[0].detach().cpu().tolist())

    checkpoint = {
        "schema_version": "uml_part4_context_checkpoint_v1",
        "model": "causal_context_character_model",
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "steps_completed": args.steps,
        "config": {
            "batch_size": args.batch_size,
            "context_length": args.context_length,
            "embedding_width": args.embedding_width,
            "attention": "uniform_causal_average",
            "position_embedding": True,
            "causal_mask": "lower_triangular",
            "learning_rate": args.learning_rate,
            "optimizer": "AdamW",
            "seed": args.seed,
            "device": str(device),
        },
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "metrics": measured,
    }
    torch.save(checkpoint, checkpoint_path)
    _json_write(
        metrics_path,
        {
            "schema_version": "uml_part4_context_metrics_v1",
            "steps_completed": args.steps,
            "fixed_batch": {
                "batch_size": args.batch_size,
                "context_length": int(inputs.shape[1]),
            },
            "measurements": measured,
        },
    )
    sample_path.write_text(
        f"prompt={prompt!r}\n"
        f"generated_token_count={args.sample_tokens}\n"
        f"text={generated_text!r}\n",
        encoding="utf-8",
        newline="\n",
    )

    run_manifest = {
        "schema_version": "uml_part4_context_run_v1",
        "status": "COMPLETE",
        "model": "causal_context_character_model",
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "dataset_dir": str(Path(args.dataset).resolve()).replace("\\", "/"),
        "steps_requested": args.steps,
        "steps_completed": args.steps,
        "fixed_batch_size": args.batch_size,
        "context_length": args.context_length,
        "embedding_width": args.embedding_width,
        "optimizer": "AdamW",
        "learning_rate": args.learning_rate,
        "attention": "uniform_causal_average",
        "position_embedding": True,
        "causal_mask": "lower_triangular",
        "seed": args.seed,
        "device": str(device),
        "training_authorized": True,
        "model_run_authorized": True,
        "aios_live_mutation": False,
        "checkpoint_sha256": _file_sha256(checkpoint_path),
        "metrics_sha256": _file_sha256(metrics_path),
        "sample_sha256": _file_sha256(sample_path),
        "initial": measured[0],
        "final": final,
        "generated_sample": str(sample_path.resolve()).replace("\\", "/"),
        "next_step": "Part 5",
    }
    _json_write(run_manifest_path, run_manifest)
    report = output / "RUN_REPORT.md"
    report.write_text(
        "# Part 4 run report\n\n"
        f"- Vocabulary size: `{tokenizer.vocab_size}`\n"
        f"- Embedding width: `{args.embedding_width}`\n"
        f"- Context length: `{args.context_length}`\n"
        "- Context aggregation: `uniform causal average`\n"
        "- Mask: `lower triangular`\n"
        f"- Fixed batch: `{args.batch_size}` x `{int(inputs.shape[1])}`\n"
        f"- Optimizer: `AdamW`, learning rate `{args.learning_rate}`\n"
        f"- Steps: `{args.steps}`\n"
        f"- Initial NLL: `{measured[0]['nll']:.6f}`\n"
        f"- Final NLL: `{final['nll']:.6f}`\n"
        f"- Final perplexity: `{final['perplexity']:.6f}`\n"
        f"- Final token accuracy: `{final['token_accuracy']:.6f}`\n"
        "- Live AIOS mutation: `false`\n\n"
        "The generated text is a sampling diagnostic, not a claim of language competence.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(run_manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
