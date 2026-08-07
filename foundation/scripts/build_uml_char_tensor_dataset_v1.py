#!/usr/bin/env python3
"""Build streaming train/validation PyTorch tensors for the CPU UML path."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.uml_char_dataset import (  # noqa: E402
    DEFAULT_CHUNK_BYTES,
    DEFAULT_CONTEXT_LENGTH,
    DEFAULT_SHARD_EXAMPLES,
    DEFAULT_STRIDE,
    UMLDatasetError,
    build_tensor_dataset,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stream explicit UTF-8 text sources through the CPU UML character "
            "tokenizer and write causal PyTorch tensor shards."
        )
    )
    parser.add_argument("--train-source", required=True, help="Train text file or directory")
    parser.add_argument(
        "--validation-source",
        required=True,
        help="Validation text file or directory",
    )
    parser.add_argument("--output-dir", required=True, help="New output directory; never overwritten")
    parser.add_argument("--context-length", type=int, default=DEFAULT_CONTEXT_LENGTH)
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    parser.add_argument("--shard-examples", type=int, default=DEFAULT_SHARD_EXAMPLES)
    parser.add_argument("--pattern", default="*.txt", help="Recursive source-file pattern")
    parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = build_tensor_dataset(
            train_source=args.train_source,
            validation_source=args.validation_source,
            output_dir=args.output_dir,
            context_length=args.context_length,
            stride=args.stride,
            shard_examples=args.shard_examples,
            pattern=args.pattern,
            encoding=args.encoding,
            chunk_bytes=args.chunk_bytes,
        )
    except (OSError, UMLDatasetError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "manifest": manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
