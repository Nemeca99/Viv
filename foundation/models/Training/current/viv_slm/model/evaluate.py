#!/usr/bin/env python3
"""Evaluate a Part 3 checkpoint over every validation tensor window."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from bigram import BigramLanguageModel  # noqa: E402
from dataset import load_tensor_shard, tensor_shards  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocab", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"validation_output_exists_refuse_overwrite:{output}")
    tokenizer = CharacterTokenizer.from_manifest(args.vocab)
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict):
        raise ValueError("checkpoint_requires_object")
    if checkpoint.get("vocab_sha256") != tokenizer.vocab_sha256:
        raise ValueError("checkpoint_vocab_hash_mismatch")
    model = BigramLanguageModel(tokenizer.vocab_size)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    total_nll = 0.0
    total_correct = 0
    total_tokens = 0
    shard_results: list[dict[str, float | int | str]] = []
    with torch.no_grad():
        for path in tensor_shards(args.dataset, "validation"):
            inputs, targets = load_tensor_shard(path, vocab_size=tokenizer.vocab_size)
            logits = model(inputs)
            flat_logits = logits.reshape(-1, tokenizer.vocab_size)
            flat_targets = targets.reshape(-1)
            per_token_nll = torch.nn.functional.cross_entropy(
                flat_logits,
                flat_targets,
                reduction="sum",
            )
            correct = int((flat_logits.argmax(dim=-1) == flat_targets).sum())
            tokens = int(flat_targets.numel())
            total_nll += float(per_token_nll)
            total_correct += correct
            total_tokens += tokens
            shard_results.append(
                {
                    "path": str(path.resolve()).replace("\\", "/"),
                    "examples": int(inputs.shape[0]),
                    "tokens": tokens,
                    "nll": float(per_token_nll) / tokens,
                    "token_accuracy": correct / tokens,
                }
            )

    result = {
        "schema_version": "uml_part3_bigram_validation_v1",
        "checkpoint": str(Path(args.checkpoint).resolve()).replace("\\", "/"),
        "vocab_size": tokenizer.vocab_size,
        "vocab_sha256": tokenizer.vocab_sha256,
        "examples": sum(int(item["examples"]) for item in shard_results),
        "tokens": total_tokens,
        "nll": total_nll / total_tokens,
        "perplexity": math.exp(total_nll / total_tokens),
        "token_accuracy": total_correct / total_tokens,
        "shards": shard_results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
