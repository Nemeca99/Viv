#!/usr/bin/env python3
"""Build V25 dual-view response-only inputs with target-focused alignment.

The broad V24 packed view remains intact.  V25 adds a second train-only view
for the unstable speech families, placing each selected prompt at position
zero and repeating those rows a bounded number of times.  Validation stays
the unchanged V24 packed response-only holdout.
"""
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
DATASET_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v24"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v25_target_focused" / "inputs"
MODEL_EXPERIMENT_ROOT = VIV_ROOT / "models" / "uml_bigram_part3"
if str(MODEL_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_EXPERIMENT_ROOT))

from tokenizer import CharacterTokenizer, write_manifest  # noqa: E402

SCHEMA_VERSION = "viv_slm_v25_target_focused_tensor_dataset_v1"
PAYLOAD_SCHEMA_VERSION = "viv_slm_response_only_tensor_dataset_v1"
INPUT_SCHEMA_VERSION = "viv_slm_v25_target_focused_inputs_v1"
STORAGE_DTYPE = torch.int16
CONTEXT_LENGTH = 128
SEQUENCE_LENGTH = CONTEXT_LENGTH + 1
SHARD_EXAMPLES = 2048
TERMINATION_MARKER = "<END>"
PAD_CHARACTER = "\n"
FOCUS_REPEATS = 8
FOCUS_INTENTS = frozenset({"greeting", "speech_style", "plain_language", "presence", "capability"})


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


def _packed_windows(rows: list[dict[str, Any]], tokenizer: CharacterTokenizer) -> tuple[list[list[int]], list[list[int]], list[list[bool]], int]:
    characters: list[str] = []
    loss_mask: list[bool] = []
    for index, row in enumerate(rows):
        if index:
            characters.append("\n")
            loss_mask.append(False)
        text = str(row["text"])
        prefix = f"User: {row['prompt']}\nViv: "
        expected_target = f"{prefix}{row['response']}\n{TERMINATION_MARKER}"
        if not text.startswith(expected_target):
            raise ValueError(f"viv_slm_v25_packed_row_shape_mismatch:{row.get('example_id')}")
        response_start = len(prefix)
        response_end = len(expected_target) - 1
        characters.extend(text)
        row_mask = [False] * len(text)
        for position in range(response_start, response_end + 1):
            row_mask[position] = True
        loss_mask.extend(row_mask)
    token_ids = tokenizer.encode("".join(characters))
    inputs: list[list[int]] = []
    targets: list[list[int]] = []
    masks: list[list[bool]] = []
    for start in range(0, len(token_ids) - CONTEXT_LENGTH):
        target_mask = loss_mask[start + 1 : start + CONTEXT_LENGTH + 1]
        if not any(target_mask):
            continue
        inputs.append(token_ids[start : start + CONTEXT_LENGTH])
        targets.append(token_ids[start + 1 : start + CONTEXT_LENGTH + 1])
        masks.append(target_mask)
    if not inputs:
        raise ValueError("viv_slm_v25_packed_split_contains_no_masked_windows")
    return inputs, targets, masks, sum(sum(mask) for mask in masks)


def _focused_chunks(row: dict[str, Any], tokenizer: CharacterTokenizer) -> list[dict[str, Any]]:
    text = str(row["text"])
    prefix = f"User: {row['prompt']}\nViv: "
    expected_target = f"{prefix}{row['response']}\n{TERMINATION_MARKER}"
    if not text.startswith(expected_target) or text[len(expected_target) :] not in ("", "\n"):
        raise ValueError(f"viv_slm_v25_focus_row_shape_mismatch:{row.get('example_id')}")
    token_ids = tokenizer.encode(text)
    if len(token_ids) != len(text):
        raise ValueError(f"viv_slm_v25_focus_character_token_length_mismatch:{row.get('example_id')}")
    response_start = len(prefix)
    response_end = len(expected_target) - 1
    if response_start > CONTEXT_LENGTH:
        raise ValueError(f"viv_slm_v25_focus_prompt_exceeds_context:{row.get('example_id')}")
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
            raise ValueError(f"viv_slm_v25_focus_empty_target_chunk:{row.get('example_id')}:{chunk_index}")
        while len(window) < SEQUENCE_LENGTH:
            window.append(tokenizer.stoi[PAD_CHARACTER])
        chunks.append(
            {
                "inputs": window[:CONTEXT_LENGTH],
                "targets": window[1:SEQUENCE_LENGTH],
                "loss_mask": target_mask + [False] * (CONTEXT_LENGTH - len(target_mask)),
                "source_example_id": str(row["example_id"]),
                "chunk_index": chunk_index,
            }
        )
        covered_positions.update(position for position in positions[1:] if position in target_positions)
        if covered_positions == target_positions:
            break
        start += CONTEXT_LENGTH
        chunk_index += 1
    if covered_positions != target_positions:
        raise ValueError(f"viv_slm_v25_focus_target_coverage_gap:{row.get('example_id')}")
    return chunks


def _is_focus_row(row: dict[str, Any]) -> bool:
    return str(row.get("surface_intent") or "") in FOCUS_INTENTS or str(row.get("concept_id") or "") == "missing_evidence"


def _write_shards(
    *,
    output: Path,
    inputs: list[list[int]],
    targets: list[list[int]],
    masks: list[list[bool]],
    view: str,
    source_ids: list[str],
    file_index_start: int = 0,
) -> list[dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=True)
    shards: list[dict[str, Any]] = []
    for start in range(0, len(inputs), SHARD_EXAMPLES):
        end = start + SHARD_EXAMPLES
        path = output / f"shard_{file_index_start + len(shards):05d}.pt"
        batch_inputs = inputs[start:end]
        batch_targets = targets[start:end]
        batch_masks = masks[start:end]
        torch.save(
            {
                "schema_version": PAYLOAD_SCHEMA_VERSION,
                "storage_dtype": str(STORAGE_DTYPE),
                "inputs": torch.tensor(batch_inputs, dtype=STORAGE_DTYPE),
                "targets": torch.tensor(batch_targets, dtype=STORAGE_DTYPE),
                "loss_mask": torch.tensor(batch_masks, dtype=torch.bool),
            },
            path,
        )
        shards.append(
            {
                "path": str(path.relative_to(output.parent)).replace("\\", "/"),
                "view": view,
                "examples": len(batch_inputs),
                "context_length": CONTEXT_LENGTH,
                "storage_dtype": str(STORAGE_DTYPE),
                "loss_mask_dtype": "torch.bool",
                "source_example_ids": source_ids[start:end],
                "masked_target_tokens": int(sum(sum(mask) for mask in batch_masks)),
            }
        )
    return shards


def _write_split(
    *,
    split: str,
    rows: list[dict[str, Any]],
    output: Path,
    tokenizer: CharacterTokenizer,
    focused: bool,
) -> dict[str, Any]:
    if not focused:
        inputs, targets, masks, masked_tokens = _packed_windows(rows, tokenizer)
        shards = _write_shards(
            output=output,
            inputs=inputs,
            targets=targets,
            masks=masks,
            view="v24_packed_base",
            source_ids=[str(row["example_id"]) for row in rows],
        )
        return {
            "rows": len(rows),
            "base_examples": len(inputs),
            "focused_examples": 0,
            "focused_rows": 0,
            "focus_repeats": 0,
            "examples": len(inputs),
            "masked_target_tokens": masked_tokens,
            "shards": shards,
        }

    base_inputs, base_targets, base_masks, base_masked = _packed_windows(rows, tokenizer)
    focus_rows = [row for row in rows if _is_focus_row(row)]
    if not focus_rows:
        raise ValueError("viv_slm_v25_focus_rows_missing")
    focused_chunks: list[dict[str, Any]] = []
    for _ in range(FOCUS_REPEATS):
        for row in focus_rows:
            focused_chunks.extend(_focused_chunks(row, tokenizer))
    focus_inputs = [item["inputs"] for item in focused_chunks]
    focus_targets = [item["targets"] for item in focused_chunks]
    focus_masks = [item["loss_mask"] for item in focused_chunks]
    base_ids = [str(row["example_id"]) for row in rows]
    focus_ids = [str(item["source_example_id"]) for item in focused_chunks]
    base_shards = _write_shards(output=output, inputs=base_inputs, targets=base_targets, masks=base_masks, view="v24_packed_base", source_ids=base_ids, file_index_start=0)
    focus_shards = _write_shards(output=output, inputs=focus_inputs, targets=focus_targets, masks=focus_masks, view="v25_position_aligned_focus", source_ids=focus_ids, file_index_start=len(base_shards))
    shards = base_shards + focus_shards
    return {
        "rows": len(rows),
        "base_examples": len(base_inputs),
        "focused_examples": len(focus_inputs),
        "focused_rows": len(focus_rows),
        "focus_repeats": FOCUS_REPEATS,
        "examples": len(base_inputs) + len(focus_inputs),
        "masked_target_tokens": base_masked + sum(sum(mask) for mask in focus_masks),
        "focused_intents": sorted({str(row.get("surface_intent") or "missing_evidence") for row in focus_rows}),
        "shards": shards,
    }


def build(*, dataset_root: Path = DATASET_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_v25_inputs_exists_refuse_overwrite:{output_dir}")
    dataset_manifest_path = dataset_root / "MANIFEST.json"
    vocab_source_path = dataset_root / "VOCAB.json"
    if not dataset_manifest_path.is_file() or not vocab_source_path.is_file():
        raise FileNotFoundError("viv_slm_v25_source_manifest_missing")
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    vocab_source = json.loads(vocab_source_path.read_text(encoding="utf-8"))
    if dataset_manifest.get("world_knowledge_included") is not False or dataset_manifest.get("termination_marker") != TERMINATION_MARKER:
        raise ValueError("viv_slm_v25_source_policy_violation")
    if vocab_source.get("vocab_size") != 96 or not isinstance(vocab_source.get("vocab"), list):
        raise ValueError("viv_slm_v25_vocab_invalid")
    train_rows = _read_jsonl(dataset_root / "train.jsonl")
    validation_rows = _read_jsonl(dataset_root / "validation.jsonl")
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = CharacterTokenizer(vocab_source["vocab"])
    source_records = [
        {"path": str(dataset_manifest_path).replace("\\", "/"), "sha256": _sha256(dataset_manifest_path)},
        {"path": str(vocab_source_path).replace("\\", "/"), "sha256": _sha256(vocab_source_path)},
    ]
    vocab_path = output_dir / "VOCAB.json"
    write_manifest(vocab_path, tokenizer, source_records=source_records, parent_vocab_sha256=vocab_source.get("vocab_sha256"))
    tensor_dir = output_dir / "tensor_dataset"
    train_manifest = _write_split(split="train", rows=train_rows, output=tensor_dir / "train", tokenizer=tokenizer, focused=True)
    validation_manifest = _write_split(split="validation", rows=validation_rows, output=tensor_dir / "validation", tokenizer=tokenizer, focused=False)
    tensor_manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
        "tokenizer": tokenizer.manifest(),
        "objective": {
            "kind": "dual_view_causal_next_character_response_only",
            "context_length": CONTEXT_LENGTH,
            "loss_mask": "assistant_response_and_end_marker_only",
            "base_view": "v24_packed_response_only",
            "focus_view": "v25_position_aligned_target_focus",
            "focus_prompt_position": 0,
            "focus_target_coverage": "complete",
            "focus_repeats": FOCUS_REPEATS,
            "validation_view": "v24_packed_response_only_unchanged",
        },
        "storage": {"dtype": str(STORAGE_DTYPE), "loss_mask_dtype": "torch.bool", "shard_examples": SHARD_EXAMPLES},
        "splits": {"train": train_manifest, "validation": validation_manifest},
        "source_policy": "v24_source_rows_read_only_plus_train_only_position_aligned_focus_view",
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
        "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
        "vocab_size": tokenizer.vocab_size,
        "context_length": CONTEXT_LENGTH,
        "termination_marker": TERMINATION_MARKER,
        "response_only_loss": True,
        "target_focused": True,
        "focus_view": "position_aligned_train_only",
        "focus_repeats": FOCUS_REPEATS,
        "focus_intents": train_manifest["focused_intents"],
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "train_examples": train_manifest["examples"],
        "base_train_examples": train_manifest["base_examples"],
        "focused_train_examples": train_manifest["focused_examples"],
        "focused_train_rows": train_manifest["focused_rows"],
        "validation_examples": validation_manifest["examples"],
        "validation_unchanged_from_v24": True,
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "next_step": "train_exactly_250_steps_from_v24_step_250_or_v17_step_250_after_named_authorization",
    }
    _json_write(output_dir / "INPUT_MANIFEST.json", input_manifest)
    return input_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(dataset_root=args.dataset_root, output_dir=args.output_dir)
    print(json.dumps({"status": "VIV_SLM_V25_TARGET_FOCUSED_INPUTS_PASS", "output_dir": str(args.output_dir).replace("\\", "/"), "train_examples": manifest["train_examples"], "base_train_examples": manifest["base_train_examples"], "focused_train_examples": manifest["focused_train_examples"], "focused_train_rows": manifest["focused_train_rows"], "validation_examples": manifest["validation_examples"], "focus_repeats": manifest["focus_repeats"], "training_authorized": manifest["training_authorized"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
