#!/usr/bin/env python3
"""Build the V43 conversation-focused replay input lane.

V42 proved that merely appending a small dialogue-context lane is too weak to
change the renderer: only 56 dialogue training windows were mixed into more
than 53k replay examples, and the governed canary retained its step-0 state.
V43 keeps the same authored identity corpus and response-only loss contract,
but applies an explicit, bounded 32x training oversample to the dialogue
windows.  Validation is not oversampled.  This isolates input visibility as
the next hypothesis while preserving the V31 replay and all CPU authority
boundaries.

The script imports the frozen V42 case/chunk implementation instead of
duplicating its tokenizer and masking logic.  It writes a new immutable input
root and refuses to overwrite any existing artifact.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from hashlib import sha256
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping, Sequence

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
V42_BUILDER_PATH = FOUNDATION / "scripts" / "build_viv_slm_dialogue_context_v41_inputs.py"
BASE_INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v31_balanced_base" / "inputs"
VOCAB_SOURCE = BASE_INPUT_ROOT / "VOCAB.json"
DEFAULT_SOURCE_ROOT = FOUNDATION / "artifacts" / "auto" / "agentic" / "viv_slm_identity_dialogue_v43"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v43_conversation_focus" / "inputs"

SCHEMA_VERSION = "viv_slm_v43_conversation_focus_replay_inputs_v1"
SOURCE_SCHEMA_VERSION = "viv_slm_v43_identity_dialogue_source_v1"
TENSOR_SCHEMA_VERSION = "viv_slm_v43_conversation_focus_tensor_dataset_v1"
CONTEXT_LENGTH = 128
STORAGE_DTYPE = torch.int16
SHARD_EXAMPLES = 2048
TERMINATION_MARKER = "<END>"
DIALOGUE_TRAIN_OVERSAMPLE = 32


def _load_v42_builder() -> Any:
    spec = importlib.util.spec_from_file_location("viv_slm_v42_dialogue_builder", V42_BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("viv_slm_v43_v42_builder_import_spec_missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8", newline="\n")


def _clone_rows(v42: Any, cases: Sequence[Mapping[str, Any]], tokenizer: Any, split: str) -> list[dict[str, Any]]:
    rows = v42._rows_for_split(cases, tokenizer, split)
    cloned: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["example_id"] = str(item["example_id"]).replace("v41-", "v43-", 1)
        item["schema_version"] = "viv_slm_v43_identity_dialogue_row_v1"
        item["source"] = "viv_slm_identity_dialogue_context_v43_oversampled"
        item["sampling_policy"] = "dialogue_train_oversample_32x" if split == "train" else "validation_once"
        cloned.append(item)
    return cloned


def _write_shards(v42: Any, output: Path, inputs: torch.Tensor, targets: torch.Tensor, masks: torch.Tensor) -> list[dict[str, Any]]:
    return v42._write_shards(output, inputs, targets, masks)


def build(*, source_root: Path = DEFAULT_SOURCE_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_v43_output_exists_refuse_overwrite:{output_dir}")
    for required in (BASE_INPUT_ROOT / "INPUT_MANIFEST.json", BASE_INPUT_ROOT / "tensor_dataset", VOCAB_SOURCE, V42_BUILDER_PATH):
        if not required.exists():
            raise FileNotFoundError(f"viv_slm_v43_source_missing:{required}")

    v42 = _load_v42_builder()
    vocab_data = json.loads(VOCAB_SOURCE.read_text(encoding="utf-8"))
    tokenizer = v42.CharacterTokenizer(vocab_data["vocab"])
    train_rows = _clone_rows(v42, v42.TRAIN_CASES, tokenizer, "train")
    validation_rows = _clone_rows(v42, v42.VALIDATION_CASES, tokenizer, "validation")
    frozen_rows = _clone_rows(v42, v42.FROZEN_CASES, tokenizer, "frozen")
    adversarial_rows = _clone_rows(v42, v42.ADVERSARIAL_CASES, tokenizer, "adversarial")
    all_rows = {"train": train_rows, "validation": validation_rows, "frozen": frozen_rows, "adversarial": adversarial_rows}

    source_root.mkdir(parents=True, exist_ok=True)
    for split, rows in all_rows.items():
        _write_jsonl(source_root / f"{split}.jsonl", rows)
    source_manifest = {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "status": "COMPLETE",
        "model": "Viv-SLM",
        "purpose": "conversation_coherence_identity_lineage_context_visibility",
        "context_format": "User_and_Viv_turns_followed_by_current_User_then_Viv_completion",
        "context_length": CONTEXT_LENGTH,
        "termination_marker": TERMINATION_MARKER,
        "response_only_loss": True,
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "telemetry_in_training_responses": False,
        "sampling_policy": {
            "train": "dialogue_context_chunks_repeated_32x_after_chunking",
            "validation": "dialogue_context_chunks_once",
            "frozen": "holdout_only",
            "adversarial": "auditor_only",
        },
        "dialogue_train_oversample": DIALOGUE_TRAIN_OVERSAMPLE,
        "splits": {split: {"rows": len(rows), "path": str((source_root / f"{split}.jsonl")).replace("\\", "/")} for split, rows in all_rows.items()},
        "source_vocab": str(VOCAB_SOURCE).replace("\\", "/"),
        "source_vocab_sha256": _sha256(VOCAB_SOURCE),
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
    }
    for split in all_rows:
        source_manifest["splits"][split]["sha256"] = _sha256(source_root / f"{split}.jsonl")
    _json_write(source_root / "MANIFEST.json", source_manifest)

    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VOCAB_SOURCE, output_dir / "VOCAB.json")
    tensor_dir = output_dir / "tensor_dataset"
    split_manifests: dict[str, Any] = {}
    for split, rows in (("train", train_rows), ("validation", validation_rows)):
        base_inputs, base_targets, base_masks = v42._load_base_split(split)
        new_chunks = [chunk for row in rows for chunk in v42._row_chunks(row, tokenizer)]
        unweighted_count = len(new_chunks)
        if split == "train":
            new_chunks = new_chunks * DIALOGUE_TRAIN_OVERSAMPLE
        new_inputs = torch.tensor([chunk["inputs"] for chunk in new_chunks], dtype=torch.long)
        new_targets = torch.tensor([chunk["targets"] for chunk in new_chunks], dtype=torch.long)
        new_masks = torch.tensor([chunk["loss_mask"] for chunk in new_chunks], dtype=torch.bool)
        inputs = torch.cat((base_inputs.long(), new_inputs), dim=0)
        targets = torch.cat((base_targets.long(), new_targets), dim=0)
        masks = torch.cat((base_masks.bool(), new_masks), dim=0)
        split_manifests[split] = {
            "base_replay_examples": int(base_inputs.shape[0]),
            "dialogue_context_examples_unweighted": unweighted_count,
            "dialogue_context_examples": int(new_inputs.shape[0]),
            "dialogue_train_oversample": DIALOGUE_TRAIN_OVERSAMPLE if split == "train" else 1,
            "examples": int(inputs.shape[0]),
            "masked_target_tokens": int(masks.sum()),
            "shards": _write_shards(v42, tensor_dir / split, inputs, targets, masks),
        }

    tensor_manifest = {
        "schema_version": TENSOR_SCHEMA_VERSION,
        "status": "COMPLETE",
        "objective": {
            "kind": "v31_replay_plus_oversampled_dialogue_context_response_only",
            "context_length": CONTEXT_LENGTH,
            "loss_mask": "Viv_response_and_end_marker_only",
            "dialogue_context": True,
            "target_coverage": "complete_response_and_end_marker",
            "sampling_policy": "train_dialogue_chunks_repeated_32x_validation_once",
        },
        "storage": {"dtype": str(STORAGE_DTYPE), "loss_mask_dtype": "torch.bool", "shard_examples": SHARD_EXAMPLES},
        "base_input_manifest": str((BASE_INPUT_ROOT / "INPUT_MANIFEST.json")).replace("\\", "/"),
        "base_input_manifest_sha256": _sha256(BASE_INPUT_ROOT / "INPUT_MANIFEST.json"),
        "dialogue_source_manifest": str((source_root / "MANIFEST.json")).replace("\\", "/"),
        "dialogue_source_manifest_sha256": _sha256(source_root / "MANIFEST.json"),
        "splits": split_manifests,
    }
    _json_write(tensor_dir / "MANIFEST.json", tensor_manifest)
    input_manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED",
        "model": "Viv-SLM",
        "base_input_root": str(BASE_INPUT_ROOT).replace("\\", "/"),
        "base_input_manifest": str((BASE_INPUT_ROOT / "INPUT_MANIFEST.json")).replace("\\", "/"),
        "dialogue_source_root": str(source_root).replace("\\", "/"),
        "dialogue_source_manifest": str((source_root / "MANIFEST.json")).replace("\\", "/"),
        "dialogue_source_manifest_sha256": _sha256(source_root / "MANIFEST.json"),
        "vocab_manifest": str((output_dir / "VOCAB.json")).replace("\\", "/"),
        "vocab_manifest_sha256": _sha256(output_dir / "VOCAB.json"),
        "tensor_manifest": str((tensor_dir / "MANIFEST.json")).replace("\\", "/"),
        "tensor_manifest_sha256": _sha256(tensor_dir / "MANIFEST.json"),
        "vocab_size": tokenizer.vocab_size,
        "context_length": CONTEXT_LENGTH,
        "termination_marker": TERMINATION_MARKER,
        "response_only_loss": True,
        "dialogue_context": True,
        "base_replay": True,
        "dialogue_train_oversample": DIALOGUE_TRAIN_OVERSAMPLE,
        "train_examples": split_manifests["train"]["examples"],
        "validation_examples": split_manifests["validation"]["examples"],
        "dialogue_context_train_examples_unweighted": split_manifests["train"]["dialogue_context_examples_unweighted"],
        "dialogue_context_train_examples": split_manifests["train"]["dialogue_context_examples"],
        "dialogue_context_validation_examples": split_manifests["validation"]["dialogue_context_examples"],
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "global_aifl_writes": False,
        "master_s_n_mutation": False,
        "knowledge_admission": False,
        "next_step": "train_exactly_one_250_step_increment_through_generic_layer_governor",
    }
    _json_write(output_dir / "INPUT_MANIFEST.json", input_manifest)
    return input_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(source_root=args.source_root, output_dir=args.output_dir)
    print(json.dumps({
        "status": "VIV_SLM_V43_CONVERSATION_FOCUS_INPUTS_PASS",
        "output_dir": str(args.output_dir).replace("\\", "/"),
        "source_root": str(args.source_root).replace("\\", "/"),
        "train_examples": manifest["train_examples"],
        "validation_examples": manifest["validation_examples"],
        "dialogue_context_train_examples_unweighted": manifest["dialogue_context_train_examples_unweighted"],
        "dialogue_context_train_examples": manifest["dialogue_context_train_examples"],
        "dialogue_context_validation_examples": manifest["dialogue_context_validation_examples"],
        "dialogue_train_oversample": manifest["dialogue_train_oversample"],
        "base_replay": manifest["base_replay"],
        "response_only_loss": manifest["response_only_loss"],
        "world_knowledge_included": manifest["world_knowledge_included"],
        "training_authorized": manifest["training_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
