#!/usr/bin/env python3
"""Build chunked dialogue-aligned tensors without truncating response targets."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
DATASET_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v17"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v21_dialogue_aligned_v2" / "inputs"
MODEL_EXPERIMENT_ROOT = VIV_ROOT / "models" / "uml_bigram_part3"
if str(MODEL_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_EXPERIMENT_ROOT))

from tokenizer import CharacterTokenizer, write_manifest  # noqa: E402

SCHEMA_VERSION = "viv_slm_dialogue_aligned_chunked_tensor_dataset_v2"
INPUT_SCHEMA_VERSION = "viv_slm_training_inputs_dialogue_aligned_chunked_v2"
STORAGE_DTYPE = torch.int16
CONTEXT_LENGTH = 128
SEQUENCE_LENGTH = CONTEXT_LENGTH + 1
SHARD_EXAMPLES = 2048
TERMINATION_MARKER = "<END>"
PAD_CHARACTER = "\n"


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _row_chunks(row: dict[str, Any], tokenizer: CharacterTokenizer) -> list[dict[str, Any]]:
    text = str(row["text"])
    prefix = f"User: {row['prompt']}\nViv: "
    expected_target = f"{prefix}{row['response']}\n{TERMINATION_MARKER}"
    if not text.startswith(expected_target) or text[len(expected_target) :] not in ("", "\n"):
        raise ValueError(f"dialogue_aligned_v2_row_shape_mismatch:{row.get('example_id')}")
    token_ids = tokenizer.encode(text)
    if len(token_ids) != len(text):
        raise ValueError(f"dialogue_aligned_v2_character_token_length_mismatch:{row.get('example_id')}")
    response_start = len(prefix)
    response_end = len(expected_target) - 1
    if response_start > CONTEXT_LENGTH:
        raise ValueError(f"dialogue_aligned_v2_prompt_exceeds_context:{row.get('example_id')}")
    target_positions = set(range(response_start, response_end + 1))
    covered_positions: set[int] = set()
    chunks: list[dict[str, Any]] = []
    start = 0
    chunk_index = 0
    while start <= response_end:
        window = token_ids[start : start + SEQUENCE_LENGTH]
        positions = list(range(start, start + len(window)))
        target_mask = [position in target_positions for position in positions[1:]]
        if not any(target_mask):
            raise ValueError(f"dialogue_aligned_v2_empty_target_chunk:{row.get('example_id')}:{chunk_index}")
        while len(window) < SEQUENCE_LENGTH:
            window.append(tokenizer.stoi[PAD_CHARACTER])
        chunks.append(
            {
                "inputs": window[:CONTEXT_LENGTH],
                "targets": window[1:SEQUENCE_LENGTH],
                "loss_mask": target_mask + [False] * (CONTEXT_LENGTH - len(target_mask)),
                "source_example_id": str(row["example_id"]),
                "chunk_index": chunk_index,
                "prompt_position": 0 if chunk_index == 0 else None,
            }
        )
        covered_positions.update(position for position in positions[1:] if position in target_positions)
        if covered_positions == target_positions:
            break
        start += CONTEXT_LENGTH
        chunk_index += 1
    if covered_positions != target_positions:
        missing = sorted(target_positions - covered_positions)
        raise ValueError(f"dialogue_aligned_v2_target_coverage_gap:{row.get('example_id')}:{missing[:5]}")
    return chunks


def _write_split(*, split: str, rows: list[dict[str, Any]], output: Path, tokenizer: CharacterTokenizer) -> dict[str, Any]:
    examples: list[dict[str, Any]] = []
    for row in rows:
        examples.extend(_row_chunks(row, tokenizer))
    output.mkdir(parents=True, exist_ok=True)
    shards: list[dict[str, Any]] = []
    for start in range(0, len(examples), SHARD_EXAMPLES):
        end = start + SHARD_EXAMPLES
        path = output / f"shard_{len(shards):05d}.pt"
        batch = examples[start:end]
        torch.save(
            {
                "schema_version": SCHEMA_VERSION,
                "storage_dtype": str(STORAGE_DTYPE),
                "inputs": torch.tensor([item["inputs"] for item in batch], dtype=STORAGE_DTYPE),
                "targets": torch.tensor([item["targets"] for item in batch], dtype=STORAGE_DTYPE),
                "loss_mask": torch.tensor([item["loss_mask"] for item in batch], dtype=torch.bool),
            },
            path,
        )
        shards.append(
            {
                "path": str(path.relative_to(output.parent)).replace("\\", "/"),
                "examples": len(batch),
                "context_length": CONTEXT_LENGTH,
                "storage_dtype": str(STORAGE_DTYPE),
                "loss_mask_dtype": "torch.bool",
                "source_example_ids": [item["source_example_id"] for item in batch],
                "chunk_indices": [item["chunk_index"] for item in batch],
                "prompt_position_zero_count": sum(item["prompt_position"] == 0 for item in batch),
                "continuation_chunk_count": sum(item["prompt_position"] is None for item in batch),
            }
        )
    return {
        "rows": len(rows),
        "examples": len(examples),
        "chunks": len(examples),
        "masked_target_tokens": sum(sum(item["loss_mask"]) for item in examples),
        "truncated_rows": [],
        "source_example_ids": [str(row["example_id"]) for row in rows],
        "shards": shards,
    }


def build(*, dataset_root: Path = DATASET_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_dialogue_aligned_v2_inputs_exists_refuse_overwrite:{output_dir}")
    dataset_manifest_path = dataset_root / "MANIFEST.json"
    vocab_source_path = dataset_root / "VOCAB.json"
    if not dataset_manifest_path.is_file() or not vocab_source_path.is_file():
        raise FileNotFoundError("viv_slm_dialogue_aligned_v2_source_manifest_missing")
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    vocab_source = json.loads(vocab_source_path.read_text(encoding="utf-8"))
    if dataset_manifest.get("world_knowledge_included") is not False:
        raise ValueError("viv_slm_dialogue_aligned_v2_world_knowledge_policy_violation")
    if dataset_manifest.get("termination_marker") != TERMINATION_MARKER:
        raise ValueError("viv_slm_dialogue_aligned_v2_termination_marker_mismatch")
    vocab = vocab_source.get("vocab")
    if vocab_source.get("vocab_size") != 96 or not isinstance(vocab, list):
        raise ValueError("viv_slm_dialogue_aligned_v2_vocab_invalid")
    split_rows = {split: _read_jsonl(dataset_root / f"{split}.jsonl") for split in ("train", "validation")}
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = CharacterTokenizer(vocab)
    source_records = [
        {"path": str(dataset_manifest_path).replace("\\", "/"), "sha256": _sha256(dataset_manifest_path)},
        {"path": str(vocab_source_path).replace("\\", "/"), "sha256": _sha256(vocab_source_path)},
    ]
    vocab_path = output_dir / "VOCAB.json"
    vocab_manifest = write_manifest(vocab_path, tokenizer, source_records=source_records, parent_vocab_sha256=vocab_source.get("vocab_sha256"))
    tensor_dir = output_dir / "tensor_dataset"
    split_manifests = {
        split: _write_split(split=split, rows=rows, output=tensor_dir / split, tokenizer=tokenizer)
        for split, rows in split_rows.items()
    }
    tensor_manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "tokenizer": tokenizer.manifest(),
        "objective": {
            "kind": "dialogue_aligned_chunked_causal_next_character_response_only",
            "context_length": CONTEXT_LENGTH,
            "sequence_length": SEQUENCE_LENGTH,
            "loss_mask": "assistant_response_and_end_marker_only",
            "first_chunk_prompt_position": 0,
            "continuation_chunk_prompt_position": None,
            "padding_character": PAD_CHARACTER,
            "padding_loss_excluded": True,
            "chunk_stride": CONTEXT_LENGTH,
            "target_coverage": "every_response_and_end_marker_character_exactly_once",
            "truncation_policy": "reject_prefix_over_context_and_fail_on_target_coverage_gap",
        },
        "storage": {"dtype": str(STORAGE_DTYPE), "loss_mask_dtype": "torch.bool", "shard_examples": SHARD_EXAMPLES},
        "splits": split_manifests,
        "source_policy": "one_prompt_response_pair_with_position_zero_first_chunk_and_loss_complete_continuations",
    }
    _json_write(tensor_dir / "MANIFEST.json", tensor_manifest)
    input_manifest = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED",
        "model": "Viv-SLM",
        "dataset_manifest": str(dataset_manifest_path).replace("\\", "/"),
        "dataset_manifest_sha256": _sha256(dataset_manifest_path),
        "vocab_manifest": str(vocab_path).replace("\\", "/"),
        "vocab_manifest_sha256": _sha256(vocab_path),
        "tensor_manifest": str(tensor_dir / "MANIFEST.json").replace("\\", "/"),
        "tensor_manifest_sha256": _sha256(tensor_dir / "MANIFEST.json"),
        "vocab_size": tokenizer.vocab_size,
        "context_length": CONTEXT_LENGTH,
        "termination_marker": TERMINATION_MARKER,
        "response_only_loss": True,
        "dialogue_aligned": True,
        "chunked": True,
        "padding_character": PAD_CHARACTER,
        "truncated_rows": 0,
        "target_coverage": "complete",
        "train_rows": split_manifests["train"]["rows"],
        "validation_rows": split_manifests["validation"]["rows"],
        "train_examples": split_manifests["train"]["examples"],
        "validation_examples": split_manifests["validation"]["examples"],
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "next_step": "train_in_250_step_increments_from_v17_step_250_warm_start_after_preflight",
    }
    _json_write(output_dir / "INPUT_MANIFEST.json", input_manifest)
    return input_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(dataset_root=args.dataset_root, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "status": "VIV_SLM_DIALOGUE_ALIGNED_CHUNKED_INPUTS_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "train_rows": manifest["train_rows"],
                "validation_rows": manifest["validation_rows"],
                "train_examples": manifest["train_examples"],
                "validation_examples": manifest["validation_examples"],
                "dialogue_aligned": manifest["dialogue_aligned"],
                "chunked": manifest["chunked"],
                "truncated_rows": manifest["truncated_rows"],
                "target_coverage": manifest["target_coverage"],
                "training_authorized": manifest["training_authorized"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
