#!/usr/bin/env python3
"""Scan source text and write an append-only Part 3 character vocabulary."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from tokenizer import CharacterTokenizer, write_manifest  # noqa: E402


def read_source(path: Path) -> tuple[str, dict[str, object]]:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="strict")
    return text, {
        "path": str(path.resolve()).replace("\\", "/"),
        "bytes": len(raw),
        "characters": len(text),
        "sha256": sha256(raw).hexdigest(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="UTF-8 text source; repeat to scan train and validation text",
    )
    parser.add_argument("--output", required=True, help="New VOCAB.json path")
    parser.add_argument(
        "--base-vocab",
        help="Existing VOCAB.json; preserve its IDs and append new characters",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = [Path(value) for value in args.source]
    texts: list[str] = []
    records: list[dict[str, object]] = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"source_not_found:{path}")
        text, record = read_source(path)
        texts.append(text)
        records.append(record)

    parent_hash: str | None = None
    if args.base_vocab:
        base = CharacterTokenizer.from_manifest(args.base_vocab)
        tokenizer = base.expanded(texts)
        parent_hash = base.vocab_sha256
    else:
        tokenizer = CharacterTokenizer.from_texts(texts)

    manifest = write_manifest(
        args.output,
        tokenizer,
        source_records=records,
        parent_vocab_sha256=parent_hash,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(Path(args.output).resolve()).replace("\\", "/"),
                "vocab_size": manifest["vocab_size"],
                "vocab_sha256": manifest["vocab_sha256"],
                "parent_vocab_sha256": parent_hash,
                "source_count": len(records),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
