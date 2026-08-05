#!/usr/bin/env python3
"""Run Part 6 architecture preflight and preserve random initialization."""
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

from dataset import first_batch  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

DEFAULT_VOCAB = HERE / "artifacts" / "run_500_steps" / "vocab" / "VOCAB.json"
DEFAULT_DATASET = HERE / "artifacts" / "run_500_steps" / "tensor_dataset"
DEFAULT_OUTPUT = HERE / "artifacts" / "part6_transformer_random_init"


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocab", default=str(DEFAULT_VOCAB))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--context-length", type=int, default=128)
    parser.add_argument("--embedding-width", type=int, default=128)
    parser.add_argument("--num-heads", type=int, default=4)
    parser.add_argument("--head-size", type=int, default=32)
    parser.add_argument("--num-layers", type=int, default=4)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "random_init.pt"
    manifest_path = output / "PREFLIGHT.json"
    for path in (checkpoint_path, manifest_path):
        if path.exists():
            raise FileExistsError(f"preflight_output_exists_refuse_overwrite:{path}")
    if args.batch_size <= 0 or args.context_length <= 0:
        raise ValueError("preflight_batch_and_context_must_be_positive")

    tokenizer = CharacterTokenizer.from_manifest(args.vocab)
    inputs, targets = first_batch(
        args.dataset,
        vocab_size=tokenizer.vocab_size,
        batch_size=args.batch_size,
    )
    if int(inputs.shape[1]) != args.context_length:
        raise ValueError("preflight_dataset_context_length_mismatch")
    torch.manual_seed(args.seed)
    model = TransformerLanguageModel(
        tokenizer.vocab_size,
        context_length=args.context_length,
        embedding_width=args.embedding_width,
        num_heads=args.num_heads,
        head_size=args.head_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
    )
    model.eval()
    with torch.no_grad():
        logits, attention = model(inputs, return_attention=True)
        loss, accuracy = model.loss_and_accuracy(logits, targets)

    attention_shapes = [
        [list(weights.shape) for weights in block_weights]
        for block_weights in attention
    ]
    upper_triangle_max = max(
        float(torch.triu(weights[0], diagonal=1).abs().max())
        for block_weights in attention
        for weights in block_weights
    )
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    checkpoint = {
        "schema_version": "uml_part6_transformer_random_init_v1",
        "model": "four_block_four_head_transformer",
        "weights_status": "random_initialization",
        "training_steps": 0,
        "seed": args.seed,
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "config": {
            "batch_size": args.batch_size,
            "context_length": args.context_length,
            "embedding_width": args.embedding_width,
            "num_heads": args.num_heads,
            "head_size": args.head_size,
            "num_layers": args.num_layers,
            "feed_forward_width": 4 * args.embedding_width,
            "dropout": args.dropout,
            "optimizer_steps": 0,
        },
        "model_state_dict": model.state_dict(),
    }
    torch.save(checkpoint, checkpoint_path)
    manifest = {
        "schema_version": "uml_part6_transformer_preflight_v1",
        "status": "PASS_RANDOM_WEIGHTS_NOT_TRAINED",
        "model": "four_block_four_head_transformer",
        "weights_status": "random_initialization",
        "training_steps": 0,
        "optimizer_created": False,
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "input_shape": list(inputs.shape),
        "target_shape": list(targets.shape),
        "logits_shape": list(logits.shape),
        "loss": float(loss),
        "perplexity": math.exp(float(loss)),
        "token_accuracy": float(accuracy),
        "parameter_count": parameter_count,
        "attention_shapes": attention_shapes,
        "attention_block_count": len(attention),
        "heads_per_block": len(attention[0]),
        "upper_triangle_max": upper_triangle_max,
        "context_length": args.context_length,
        "embedding_width": args.embedding_width,
        "num_heads": args.num_heads,
        "head_size": args.head_size,
        "num_layers": args.num_layers,
        "feed_forward_width": 4 * args.embedding_width,
        "dropout": args.dropout,
        "random_init_sha256": _file_sha256(checkpoint_path),
        "aios_live_mutation": False,
        "next_step": "Part 7",
    }
    _json_write(manifest_path, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
