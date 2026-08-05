#!/usr/bin/env python3
"""Build Part 3 causal character tensors from a scanned vocabulary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from dataset import (  # noqa: E402
    DEFAULT_CONTEXT_LENGTH,
    DEFAULT_SHARD_EXAMPLES,
    DEFAULT_STRIDE,
    build_tensor_dataset,
)
from tokenizer import CharacterTokenizer  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocab", required=True, help="VOCAB.json from build_vocab.py")
    parser.add_argument("--train-source", action="append", required=True)
    parser.add_argument("--validation-source", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--context-length", type=int, default=DEFAULT_CONTEXT_LENGTH)
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    parser.add_argument("--shard-examples", type=int, default=DEFAULT_SHARD_EXAMPLES)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tokenizer = CharacterTokenizer.from_manifest(args.vocab)
    manifest = build_tensor_dataset(
        train_sources=[Path(value) for value in args.train_source],
        validation_sources=[Path(value) for value in args.validation_source],
        output_dir=args.output_dir,
        tokenizer=tokenizer,
        context_length=args.context_length,
        stride=args.stride,
        shard_examples=args.shard_examples,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "output_dir": str(Path(args.output_dir).resolve()).replace("\\", "/"),
                "vocab_size": tokenizer.vocab_size,
                "train_examples": manifest["splits"]["train"]["examples"],
                "validation_examples": manifest["splits"]["validation"]["examples"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
