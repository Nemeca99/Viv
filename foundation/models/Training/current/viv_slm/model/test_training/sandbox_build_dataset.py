#!/usr/bin/env python3
"""Build sandbox tensor dataset + shared vocab from data/identity_corpus.txt.

Writes only under test_training/. Does not touch Codex/operator trees.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from dataset import build_tensor_dataset  # noqa: E402
from sandbox_paths import (  # noqa: E402
    CAMPAIGN_CFG,
    CORPUS_FILE,
    DATASET_DIR,
    SHARED_DIR,
    VOCAB_MANIFEST,
)
from tokenizer import CharacterTokenizer  # noqa: E402


def _read_corpus(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"sandbox_corpus_missing:{path}")
    lines = [
        line.strip() + "\n"
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        raise ValueError("sandbox_corpus_empty")
    return lines


def _split_sources(lines: list[str], *, val_ratio: float = 0.2) -> tuple[list[Path], list[Path]]:
    """Write temp split files under shared/ for dataset builder."""
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    n_val = max(1, int(len(lines) * val_ratio))
    train_lines = lines[:-n_val] if len(lines) > n_val else lines
    val_lines = lines[-n_val:]
    train_path = SHARED_DIR / "_train_corpus.txt"
    val_path = SHARED_DIR / "_val_corpus.txt"
    train_path.write_text("".join(train_lines), encoding="utf-8", newline="\n")
    val_path.write_text("".join(val_lines), encoding="utf-8", newline="\n")
    return [train_path], [val_path]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(CORPUS_FILE))
    parser.add_argument("--output", default=str(DATASET_DIR))
    parser.add_argument("--context-length", type=int, default=CAMPAIGN_CFG["context_length"])
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--shard-examples", type=int, default=512)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove existing dataset dir before rebuild.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    if output.exists():
        if not args.force:
            print(f"VIV_SANDBOX_DATASET_EXISTS {output} (use --force to rebuild)")
            return 0
        shutil.rmtree(output)

    corpus_path = Path(args.corpus)
    lines = _read_corpus(corpus_path)
    tok = CharacterTokenizer.from_texts(lines)
    manifest = tok.manifest()
    manifest.update(
        {
            "status": "COMPLETE",
            "purpose": "sandbox_shared_identity_vocab",
            "sandbox_only": True,
            "originals_untouched": True,
            "source_corpus": str(corpus_path).replace("\\", "/"),
            "line_count": len(lines),
        }
    )
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    with VOCAB_MANIFEST.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    train_sources, val_sources = _split_sources(lines)
    ds_manifest = build_tensor_dataset(
        train_sources=train_sources,
        validation_sources=val_sources,
        output_dir=output,
        tokenizer=tok,
        context_length=int(args.context_length),
        stride=int(args.stride),
        shard_examples=int(args.shard_examples),
    )
    summary = {
        "schema_version": "viv_slm_sandbox_dataset_build_v1",
        "sandbox_only": True,
        "originals_untouched": True,
        "status": "PASS",
        "vocab_size": tok.vocab_size,
        "vocab_sha256": tok.vocab_sha256,
        "corpus_lines": len(lines),
        "train_examples": ds_manifest["splits"]["train"]["examples"],
        "validation_examples": ds_manifest["splits"]["validation"]["examples"],
        "dataset_dir": str(output).replace("\\", "/"),
        "vocab_manifest": str(VOCAB_MANIFEST).replace("\\", "/"),
    }
    summary_path = output / "sandbox_build_summary.json"
    with summary_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"VIV_SANDBOX_DATASET_PASS "
        f"vocab={tok.vocab_size} train={summary['train_examples']} "
        f"val={summary['validation_examples']} path={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
