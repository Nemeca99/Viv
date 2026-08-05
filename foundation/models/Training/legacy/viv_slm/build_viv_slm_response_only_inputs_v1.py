#!/usr/bin/env python3
"""Build response-only masked tensors for the Viv-SLM repair corpus."""
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
DATASET_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v3"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v3_response_only" / "inputs"
MODEL_EXPERIMENT_ROOT = VIV_ROOT / "models" / "uml_bigram_part3"
if str(MODEL_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_EXPERIMENT_ROOT))

from tokenizer import CharacterTokenizer, write_manifest  # noqa: E402

SCHEMA_VERSION = "viv_slm_response_only_tensor_dataset_v1"
STORAGE_DTYPE = torch.int16
CONTEXT_LENGTH = 128
STRIDE = 1
SHARD_EXAMPLES = 2048
TERMINATION_MARKER = "<END>"


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


def _pack_rows(rows: list[dict[str, Any]]) -> tuple[str, list[bool]]:
    characters: list[str] = []
    loss_mask: list[bool] = []
    for index, row in enumerate(rows):
        if index:
            characters.append("\n")
            loss_mask.append(False)
        text = str(row["text"])
        prefix = f"User: {row['prompt']}\nViv: "
        expected_target = f"{prefix}{row['response']}\n{TERMINATION_MARKER}"
        if not text.startswith(prefix) or not text.startswith(expected_target):
            raise ValueError(f"response_only_row_shape_mismatch:{row.get('example_id')}")
        response_start = len(prefix)
        response_end = len(expected_target) - 1
        characters.extend(text)
        row_mask = [False] * len(text)
        for position in range(response_start, response_end + 1):
            row_mask[position] = True
        loss_mask.extend(row_mask)
    return "".join(characters), loss_mask


def _windows(
    token_ids: list[int],
    character_mask: list[bool],
) -> tuple[list[list[int]], list[list[int]], list[list[bool]]]:
    if len(token_ids) != len(character_mask):
        raise ValueError("response_only_token_mask_length_mismatch")
    inputs: list[list[int]] = []
    targets: list[list[int]] = []
    masks: list[list[bool]] = []
    for start in range(0, len(token_ids) - CONTEXT_LENGTH):
        target_mask = character_mask[start + 1 : start + CONTEXT_LENGTH + 1]
        if not any(target_mask):
            continue
        inputs.append(token_ids[start : start + CONTEXT_LENGTH])
        targets.append(token_ids[start + 1 : start + CONTEXT_LENGTH + 1])
        masks.append(target_mask)
    if not inputs:
        raise ValueError("response_only_split_contains_no_masked_windows")
    return inputs, targets, masks


def _write_split(
    *,
    split: str,
    rows: list[dict[str, Any]],
    output: Path,
    tokenizer: CharacterTokenizer,
) -> dict[str, Any]:
    stream, character_mask = _pack_rows(rows)
    token_ids = tokenizer.encode(stream)
    inputs, targets, masks = _windows(token_ids, character_mask)
    output.mkdir(parents=True, exist_ok=True)
    shards: list[dict[str, Any]] = []
    for start in range(0, len(inputs), SHARD_EXAMPLES):
        end = start + SHARD_EXAMPLES
        path = output / f"shard_{len(shards):05d}.pt"
        torch.save(
            {
                "schema_version": SCHEMA_VERSION,
                "storage_dtype": str(STORAGE_DTYPE),
                "inputs": torch.tensor(inputs[start:end], dtype=STORAGE_DTYPE),
                "targets": torch.tensor(targets[start:end], dtype=STORAGE_DTYPE),
                "loss_mask": torch.tensor(masks[start:end], dtype=torch.bool),
            },
            path,
        )
        shards.append(
            {
                "path": str(path.relative_to(output.parent)).replace("\\", "/"),
                "examples": min(SHARD_EXAMPLES, len(inputs) - start),
                "context_length": CONTEXT_LENGTH,
                "storage_dtype": str(STORAGE_DTYPE),
                "loss_mask_dtype": "torch.bool",
            }
        )
    return {
        "rows": len(rows),
        "stream_characters": len(stream),
        "examples": len(inputs),
        "masked_target_tokens": sum(sum(mask) for mask in masks),
        "source_example_ids": [str(row["example_id"]) for row in rows],
        "shards": shards,
    }


def build(*, dataset_root: Path = DATASET_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_response_only_inputs_exists_refuse_overwrite:{output_dir}")
    dataset_manifest_path = dataset_root / "MANIFEST.json"
    vocab_source_path = dataset_root / "VOCAB.json"
    if not dataset_manifest_path.is_file() or not vocab_source_path.is_file():
        raise FileNotFoundError("viv_slm_response_only_source_manifest_missing")
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    vocab_source = json.loads(vocab_source_path.read_text(encoding="utf-8"))
    if dataset_manifest.get("world_knowledge_included") is not False:
        raise ValueError("viv_slm_response_only_world_knowledge_policy_violation")
    if dataset_manifest.get("termination_marker") != TERMINATION_MARKER:
        raise ValueError("viv_slm_response_only_termination_marker_mismatch")
    if vocab_source.get("vocab_size") != 96:
        raise ValueError("viv_slm_response_only_expected_vocab_size_96")
    vocab = vocab_source.get("vocab")
    if not isinstance(vocab, list):
        raise ValueError("viv_slm_response_only_vocab_missing")

    split_rows = {
        split: _read_jsonl(dataset_root / f"{split}.jsonl")
        for split in ("train", "validation")
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = CharacterTokenizer(vocab)
    source_records = [
        {"path": str(dataset_manifest_path).replace("\\", "/"), "sha256": _sha256(dataset_manifest_path)},
        {"path": str(vocab_source_path).replace("\\", "/"), "sha256": _sha256(vocab_source_path)},
    ]
    vocab_path = output_dir / "VOCAB.json"
    vocab_manifest = write_manifest(
        vocab_path,
        tokenizer,
        source_records=source_records,
        parent_vocab_sha256=vocab_source.get("vocab_sha256"),
    )
    tensor_dir = output_dir / "tensor_dataset"
    split_manifests = {
        split: _write_split(
            split=split,
            rows=rows,
            output=tensor_dir / split,
            tokenizer=tokenizer,
        )
        for split, rows in split_rows.items()
    }
    tensor_manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "tokenizer": tokenizer.manifest(),
        "objective": {
            "kind": "causal_next_character_response_only",
            "context_length": CONTEXT_LENGTH,
            "stride": STRIDE,
            "loss_mask": "assistant_response_and_end_marker_only",
            "input_ids": "tokens[start:start+context_length]",
            "target_ids": "tokens[start+1:start+context_length+1]",
            "ignored_target_positions": "user_prompt_and_inter-row_separator",
        },
        "storage": {
            "dtype": str(STORAGE_DTYPE),
            "loss_mask_dtype": "torch.bool",
            "model_batch_dtype": "torch.long",
            "shard_examples": SHARD_EXAMPLES,
        },
        "splits": split_manifests,
        "source_policy": "source_rows_read_only_strict_utf8_response_only_loss",
    }
    _json_write(tensor_dir / "MANIFEST.json", tensor_manifest)
    input_manifest = {
        "schema_version": "viv_slm_training_inputs_response_only_v1",
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
        "stride": STRIDE,
        "termination_marker": TERMINATION_MARKER,
        "response_only_loss": True,
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
        "next_step": "train_in_250_step_increments_from_fresh_initialization",
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
                "status": "VIV_SLM_RESPONSE_ONLY_INPUTS_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "train_examples": manifest["train_examples"],
                "validation_examples": manifest["validation_examples"],
                "response_only_loss": manifest["response_only_loss"],
                "termination_marker": manifest["termination_marker"],
                "world_knowledge_included": manifest["world_knowledge_included"],
                "training_authorized": manifest["training_authorized"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
