#!/usr/bin/env python3
"""Prepare model-compatible tokenizer and causal tensors for Viv-SLM v1."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
DATASET_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v1"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v1" / "inputs"
MODEL_EXPERIMENT_ROOT = VIV_ROOT / "models" / "uml_bigram_part3"
if str(MODEL_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_EXPERIMENT_ROOT))

from dataset import build_tensor_dataset  # noqa: E402
from tokenizer import CharacterTokenizer, write_manifest  # noqa: E402


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def build(*, dataset_root: Path = DATASET_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_training_inputs_exists_refuse_overwrite:{output_dir}")
    source_manifest_path = dataset_root / "MANIFEST.json"
    vocab_source_path = dataset_root / "VOCAB.json"
    train_source = dataset_root / "text" / "train.txt"
    validation_source = dataset_root / "text" / "validation.txt"
    for path in (source_manifest_path, vocab_source_path, train_source, validation_source):
        if not path.is_file():
            raise FileNotFoundError(f"viv_slm_training_input_missing:{path}")

    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    vocab_source = json.loads(vocab_source_path.read_text(encoding="utf-8"))
    if source_manifest.get("world_knowledge_included") is not False:
        raise ValueError("viv_slm_training_input_world_knowledge_policy_violation")
    if vocab_source.get("vocab_size") != 96:
        raise ValueError("viv_slm_training_input_expected_english_vocab_size_96")
    termination_marker = source_manifest.get("termination_marker")
    if termination_marker is not None and not isinstance(termination_marker, str):
        raise ValueError("viv_slm_training_input_termination_marker_invalid")
    vocab = vocab_source.get("vocab")
    if not isinstance(vocab, list):
        raise ValueError("viv_slm_training_input_vocab_missing")

    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = CharacterTokenizer(vocab)
    source_records = []
    for path in (train_source, validation_source):
        raw = path.read_bytes()
        source_records.append(
            {
                "path": str(path.resolve()).replace("\\", "/"),
                "bytes": len(raw),
                "characters": len(raw.decode("utf-8")),
                "sha256": sha256(raw).hexdigest(),
            }
        )
    vocab_path = output_dir / "VOCAB.json"
    vocab_manifest = write_manifest(
        vocab_path,
        tokenizer,
        source_records=source_records,
        parent_vocab_sha256=vocab_source.get("vocab_sha256"),
    )
    tensor_dir = output_dir / "tensor_dataset"
    tensor_manifest = build_tensor_dataset(
        train_sources=[train_source],
        validation_sources=[validation_source],
        output_dir=tensor_dir,
        tokenizer=tokenizer,
        context_length=128,
        stride=1,
        shard_examples=2048,
    )
    manifest = {
        "schema_version": "viv_slm_training_inputs_v1",
        "status": "COMPLETE_TRAINING_CLOSED",
        "model": "Viv-SLM",
        "dataset_manifest": str(source_manifest_path).replace("\\", "/"),
        "dataset_manifest_sha256": _sha256(source_manifest_path),
        "vocab_manifest": str(vocab_path).replace("\\", "/"),
        "vocab_manifest_sha256": _sha256(vocab_path),
        "tensor_manifest": str(tensor_dir / "MANIFEST.json").replace("\\", "/"),
        "tensor_manifest_sha256": _sha256(tensor_dir / "MANIFEST.json"),
        "vocab_size": tokenizer.vocab_size,
        "context_length": 128,
        "stride": 1,
        "termination_marker": termination_marker,
        "train_examples": tensor_manifest["splits"]["train"]["examples"],
        "validation_examples": tensor_manifest["splits"]["validation"]["examples"],
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "next_step": "train_in_250_step_increments_from_fresh_initialization",
    }
    _json_write(output_dir / "INPUT_MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(dataset_root=args.dataset_root, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "status": "VIV_SLM_TRAINING_INPUTS_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "vocab_size": manifest["vocab_size"],
                "train_examples": manifest["train_examples"],
                "validation_examples": manifest["validation_examples"],
                "world_knowledge_included": manifest["world_knowledge_included"],
                "training_authorized": manifest["training_authorized"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
