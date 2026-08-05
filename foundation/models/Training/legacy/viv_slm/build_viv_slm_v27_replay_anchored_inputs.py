#!/usr/bin/env python3
"""Build V27 inputs anchored to the original V17 replay lane.

The V24 source rows provide a small train-only surface focus, but the packed
base and validation splits are rebuilt from V17 so the canary preserves the
behavior candidate's original replay distribution.
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
SCRIPT_ROOT = FOUNDATION / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import build_viv_slm_v25_target_focused_inputs as _v25  # noqa: E402

BASE_DATASET_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v17"
FOCUS_DATASET_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v24"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v27_replay_anchored" / "inputs"
SCHEMA_VERSION = "viv_slm_v27_replay_anchored_tensor_dataset_v1"
INPUT_SCHEMA_VERSION = "viv_slm_v27_replay_anchored_inputs_v1"
FOCUS_REPEATS = 8
FOCUS_INTENTS = frozenset({"greeting", "presence", "plain_language", "speech_style"})
FOCUS_CONCEPTS = frozenset({"gpu_renderer"})
STORAGE_DTYPE = torch.int16


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _is_focus_row(row: dict[str, Any]) -> bool:
    return str(row.get("surface_intent") or "") in FOCUS_INTENTS or str(row.get("concept_id") or "") in FOCUS_CONCEPTS


def _write_split_shards(
    *,
    output: Path,
    inputs: list[list[int]],
    targets: list[list[int]],
    masks: list[list[bool]],
    view: str,
    source_ids: list[str],
    file_index_start: int = 0,
) -> list[dict[str, Any]]:
    return _v25._write_shards(
        output=output,
        inputs=inputs,
        targets=targets,
        masks=masks,
        view=view,
        source_ids=source_ids,
        file_index_start=file_index_start,
    )


def build(*, base_dataset_root: Path = BASE_DATASET_ROOT, focus_dataset_root: Path = FOCUS_DATASET_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_v27_inputs_exists_refuse_overwrite:{output_dir}")
    base_manifest_path = base_dataset_root / "MANIFEST.json"
    focus_manifest_path = focus_dataset_root / "MANIFEST.json"
    base_vocab_path = base_dataset_root / "VOCAB.json"
    for path in (base_manifest_path, focus_manifest_path, base_vocab_path):
        if not path.is_file():
            raise FileNotFoundError(f"viv_slm_v27_source_missing:{path}")
    base_manifest = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    focus_manifest = json.loads(focus_manifest_path.read_text(encoding="utf-8"))
    vocab_source = json.loads(base_vocab_path.read_text(encoding="utf-8"))
    if base_manifest.get("world_knowledge_included") is not False or focus_manifest.get("world_knowledge_included") is not False:
        raise ValueError("viv_slm_v27_world_knowledge_policy_violation")
    if vocab_source.get("vocab_size") != 96 or not isinstance(vocab_source.get("vocab"), list):
        raise ValueError("viv_slm_v27_vocab_invalid")
    train_rows = _read_jsonl(base_dataset_root / "train.jsonl")
    validation_rows = _read_jsonl(base_dataset_root / "validation.jsonl")
    focus_rows_all = _read_jsonl(focus_dataset_root / "train.jsonl")
    focus_rows = [row for row in focus_rows_all if _is_focus_row(row)]
    if len(focus_rows) != 57:
        raise ValueError(f"viv_slm_v27_focus_row_count:{len(focus_rows)}")
    validation_ids = {str(row["example_id"]) for row in _read_jsonl(focus_dataset_root / "validation.jsonl")}
    if validation_ids.intersection({str(row["example_id"]) for row in focus_rows}):
        raise ValueError("viv_slm_v27_focus_validation_overlap")

    tokenizer = _v25.CharacterTokenizer(vocab_source["vocab"])
    base_train_inputs, base_train_targets, base_train_masks, base_train_masked = _v25._packed_windows(train_rows, tokenizer)
    validation_inputs, validation_targets, validation_masks, validation_masked = _v25._packed_windows(validation_rows, tokenizer)
    focus_chunks: list[dict[str, Any]] = []
    for _ in range(FOCUS_REPEATS):
        for row in focus_rows:
            focus_chunks.extend(_v25._focused_chunks(row, tokenizer))
    focus_inputs = [item["inputs"] for item in focus_chunks]
    focus_targets = [item["targets"] for item in focus_chunks]
    focus_masks = [item["loss_mask"] for item in focus_chunks]

    output_dir.mkdir(parents=True, exist_ok=True)
    vocab_path = output_dir / "VOCAB.json"
    _v25.write_manifest(vocab_path, tokenizer, source_records=[
        {"path": str(base_vocab_path).replace("\\", "/"), "sha256": _sha256(base_vocab_path)},
        {"path": str(focus_manifest_path).replace("\\", "/"), "sha256": _sha256(focus_manifest_path)},
    ], parent_vocab_sha256=vocab_source.get("vocab_sha256"))
    tensor_dir = output_dir / "tensor_dataset"
    base_train_ids = [str(row["example_id"]) for row in train_rows]
    focus_ids = [str(item["source_example_id"]) for item in focus_chunks]
    validation_ids_ordered = [str(row["example_id"]) for row in validation_rows]
    base_train_shards = _write_split_shards(output=tensor_dir / "train", inputs=base_train_inputs, targets=base_train_targets, masks=base_train_masks, view="v17_replay_base", source_ids=base_train_ids)
    focus_shards = _write_split_shards(output=tensor_dir / "train", inputs=focus_inputs, targets=focus_targets, masks=focus_masks, view="v27_small_surface_focus", source_ids=focus_ids, file_index_start=len(base_train_shards))
    validation_shards = _write_split_shards(output=tensor_dir / "validation", inputs=validation_inputs, targets=validation_targets, masks=validation_masks, view="v17_replay_validation", source_ids=validation_ids_ordered)
    tensor_manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "payload_schema_version": _v25.PAYLOAD_SCHEMA_VERSION,
        "tokenizer": tokenizer.manifest(),
        "objective": {
            "kind": "v17_replay_plus_small_surface_focus_causal_next_character_response_only",
            "context_length": _v25.CONTEXT_LENGTH,
            "loss_mask": "assistant_response_and_end_marker_only",
            "base_view": "v17_packed_response_only",
            "focus_view": "v27_small_surface_discrimination_train_only",
            "focus_prompt_position": 0,
            "focus_target_coverage": "complete",
            "focus_repeats": FOCUS_REPEATS,
            "focus_intents": sorted(FOCUS_INTENTS),
            "focus_concepts": sorted(FOCUS_CONCEPTS),
            "validation_view": "v17_packed_response_only_unchanged",
        },
        "storage": {"dtype": str(STORAGE_DTYPE), "loss_mask_dtype": "torch.bool", "shard_examples": _v25.SHARD_EXAMPLES},
        "splits": {
            "train": {
                "rows": len(train_rows),
                "base_examples": len(base_train_inputs),
                "focused_examples": len(focus_inputs),
                "focused_rows": len(focus_rows),
                "examples": len(base_train_inputs) + len(focus_inputs),
                "masked_target_tokens": base_train_masked + sum(sum(mask) for mask in focus_masks),
                "focused_intents": sorted(FOCUS_INTENTS),
                "focused_concepts": sorted(FOCUS_CONCEPTS),
                "shards": base_train_shards + focus_shards,
            },
            "validation": {
                "rows": len(validation_rows),
                "base_examples": len(validation_inputs),
                "focused_examples": 0,
                "focused_rows": 0,
                "examples": len(validation_inputs),
                "masked_target_tokens": validation_masked,
                "shards": validation_shards,
            },
        },
        "sources": {
            "base_dataset_manifest": str(base_manifest_path).replace("\\", "/"),
            "base_dataset_manifest_sha256": _sha256(base_manifest_path),
            "focus_dataset_manifest": str(focus_manifest_path).replace("\\", "/"),
            "focus_dataset_manifest_sha256": _sha256(focus_manifest_path),
        },
        "source_policy": "v17_replay_base_plus_v24_train_only_small_surface_focus",
    }
    tensor_manifest_path = tensor_dir / "MANIFEST.json"
    _write_json(tensor_manifest_path, tensor_manifest)
    input_manifest = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED",
        "model": "Viv-SLM",
        "base_dataset_manifest": str(base_manifest_path).replace("\\", "/"),
        "base_dataset_manifest_sha256": _sha256(base_manifest_path),
        "focus_dataset_manifest": str(focus_manifest_path).replace("\\", "/"),
        "focus_dataset_manifest_sha256": _sha256(focus_manifest_path),
        "vocab_manifest": str(vocab_path).replace("\\", "/"),
        "vocab_manifest_sha256": _sha256(vocab_path),
        "tensor_manifest": str(tensor_manifest_path).replace("\\", "/"),
        "tensor_manifest_sha256": _sha256(tensor_manifest_path),
        "payload_schema_version": _v25.PAYLOAD_SCHEMA_VERSION,
        "vocab_size": tokenizer.vocab_size,
        "context_length": _v25.CONTEXT_LENGTH,
        "termination_marker": _v25.TERMINATION_MARKER,
        "response_only_loss": True,
        "base_replay": "v17_original_packed_response_only",
        "focus_view": "v27_small_surface_discrimination_train_only",
        "focus_repeats": FOCUS_REPEATS,
        "focus_intents": sorted(FOCUS_INTENTS),
        "focus_concepts": sorted(FOCUS_CONCEPTS),
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "train_examples": len(base_train_inputs) + len(focus_inputs),
        "base_train_examples": len(base_train_inputs),
        "focused_train_examples": len(focus_inputs),
        "focused_train_rows": len(focus_rows),
        "validation_examples": len(validation_inputs),
        "validation_unchanged_from_v17": True,
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "next_step": "train_exactly_250_steps_from_v17_step_250_after_named_authorization",
    }
    _write_json(output_dir / "INPUT_MANIFEST.json", input_manifest)
    return input_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dataset-root", type=Path, default=BASE_DATASET_ROOT)
    parser.add_argument("--focus-dataset-root", type=Path, default=FOCUS_DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(base_dataset_root=args.base_dataset_root, focus_dataset_root=args.focus_dataset_root, output_dir=args.output_dir)
    print(json.dumps({
        "status": "VIV_SLM_V27_REPLAY_ANCHORED_INPUTS_PASS",
        "output_dir": str(args.output_dir).replace("\\", "/"),
        "train_examples": manifest["train_examples"],
        "base_train_examples": manifest["base_train_examples"],
        "focused_train_examples": manifest["focused_train_examples"],
        "focused_train_rows": manifest["focused_train_rows"],
        "validation_examples": manifest["validation_examples"],
        "focus_repeats": manifest["focus_repeats"],
        "training_authorized": manifest["training_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
