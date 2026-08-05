#!/usr/bin/env python3
"""Build a parameterized, response-only dialogue-weighted replay lane.

V43 showed that making dialogue context visible can improve conversational
coherence, but its 32x lane was only a small fraction of the large replay
set.  This builder keeps the V41 authored cases and tensor contract intact
while making the train weighting an explicit campaign parameter.  Validation
is always included once and the base replay remains present.

The builder is input preparation only.  It never opens training authority,
changes a checkpoint, mutates live runtime state, or writes global AIFL data.
Existing output roots are never overwritten.
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
BASE_BUILDER_PATH = FOUNDATION / "scripts" / "build_viv_slm_dialogue_context_v41_inputs.py"
BASE_INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v31_balanced_base" / "inputs"
VOCAB_SOURCE = BASE_INPUT_ROOT / "VOCAB.json"
DEFAULT_SOURCE_ROOT = FOUNDATION / "artifacts" / "auto" / "agentic" / "viv_slm_identity_dialogue_weighted"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_weighted_dialogue" / "inputs"
SCHEMA_VERSION = "viv_slm_weighted_dialogue_replay_inputs_v1"
SOURCE_SCHEMA_VERSION = "viv_slm_weighted_dialogue_source_v1"
TENSOR_SCHEMA_VERSION = "viv_slm_weighted_dialogue_tensor_dataset_v1"
CONTEXT_LENGTH = 128
STORAGE_DTYPE = torch.int16
SHARD_EXAMPLES = 2048
TERMINATION_MARKER = "<END>"


def _load_base_builder() -> Any:
    spec = importlib.util.spec_from_file_location("viv_slm_weighted_v41_builder", BASE_BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("viv_slm_weighted_base_builder_import_spec_missing")
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
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8", newline="\n")


def _clone_rows(
    base: Any,
    cases: Sequence[Mapping[str, Any]],
    tokenizer: Any,
    split: str,
    oversample: int,
) -> list[dict[str, Any]]:
    rows = base._rows_for_split(cases, tokenizer, split)
    cloned: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["example_id"] = str(item["example_id"]).replace("v41-", "weighted-", 1)
        item["schema_version"] = "viv_slm_weighted_dialogue_row_v1"
        item["source"] = "viv_slm_weighted_dialogue_context"
        item["sampling_policy"] = (
            f"dialogue_train_oversample_{oversample}x" if split == "train" else "validation_once"
        )
        cloned.append(item)
    return cloned


def build(
    *,
    oversample: int,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    if isinstance(oversample, bool) or oversample <= 0:
        raise ValueError("viv_slm_weighted_oversample_must_be_positive")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_weighted_output_exists_refuse_overwrite:{output_dir}")
    if source_root.exists() and any(source_root.iterdir()):
        raise FileExistsError(f"viv_slm_weighted_source_exists_refuse_overwrite:{source_root}")
    for required in (
        BASE_INPUT_ROOT / "INPUT_MANIFEST.json",
        BASE_INPUT_ROOT / "tensor_dataset",
        VOCAB_SOURCE,
        BASE_BUILDER_PATH,
    ):
        if not required.exists():
            raise FileNotFoundError(f"viv_slm_weighted_source_missing:{required}")

    base = _load_base_builder()
    vocab_data = json.loads(VOCAB_SOURCE.read_text(encoding="utf-8"))
    tokenizer = base.CharacterTokenizer(vocab_data["vocab"])
    train_rows = _clone_rows(base, base.TRAIN_CASES, tokenizer, "train", oversample)
    validation_rows = _clone_rows(base, base.VALIDATION_CASES, tokenizer, "validation", oversample)
    frozen_rows = _clone_rows(base, base.FROZEN_CASES, tokenizer, "frozen", oversample)
    adversarial_rows = _clone_rows(base, base.ADVERSARIAL_CASES, tokenizer, "adversarial", oversample)
    all_rows = {
        "train": train_rows,
        "validation": validation_rows,
        "frozen": frozen_rows,
        "adversarial": adversarial_rows,
    }

    source_root.mkdir(parents=True, exist_ok=True)
    for split, rows in all_rows.items():
        _write_jsonl(source_root / f"{split}.jsonl", rows)
    source_manifest = {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "status": "COMPLETE",
        "model": "Viv-SLM",
        "purpose": "current_turn_discrimination_by_dialogue_visibility",
        "context_format": "User_and_Viv_turns_followed_by_current_User_then_Viv_completion",
        "context_length": CONTEXT_LENGTH,
        "termination_marker": TERMINATION_MARKER,
        "response_only_loss": True,
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "telemetry_in_training_responses": False,
        "sampling_policy": {
            "train": f"base_replay_plus_dialogue_chunks_repeated_{oversample}x",
            "validation": "base_replay_plus_dialogue_chunks_once",
            "frozen": "holdout_only",
            "adversarial": "auditor_only",
        },
        "dialogue_train_oversample": oversample,
        "splits": {
            split: {
                "rows": len(rows),
                "path": str(source_root / f"{split}.jsonl").replace("\\", "/"),
            }
            for split, rows in all_rows.items()
        },
        "source_vocab": str(VOCAB_SOURCE).replace("\\", "/"),
        "source_vocab_sha256": _sha256(VOCAB_SOURCE),
        "base_builder": str(BASE_BUILDER_PATH).replace("\\", "/"),
        "base_builder_sha256": _sha256(BASE_BUILDER_PATH),
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
        base_inputs, base_targets, base_masks = base._load_base_split(split)
        dialogue_chunks = [chunk for row in rows for chunk in base._row_chunks(row, tokenizer)]
        unweighted_count = len(dialogue_chunks)
        weighted_chunks = dialogue_chunks * oversample if split == "train" else dialogue_chunks
        new_inputs = torch.tensor([chunk["inputs"] for chunk in weighted_chunks], dtype=torch.long)
        new_targets = torch.tensor([chunk["targets"] for chunk in weighted_chunks], dtype=torch.long)
        new_masks = torch.tensor([chunk["loss_mask"] for chunk in weighted_chunks], dtype=torch.bool)
        inputs = torch.cat((base_inputs.long(), new_inputs), dim=0)
        targets = torch.cat((base_targets.long(), new_targets), dim=0)
        masks = torch.cat((base_masks.bool(), new_masks), dim=0)
        split_manifests[split] = {
            "base_replay_examples": int(base_inputs.shape[0]),
            "dialogue_context_examples_unweighted": unweighted_count,
            "dialogue_context_examples": int(new_inputs.shape[0]),
            "dialogue_train_oversample": oversample if split == "train" else 1,
            "examples": int(inputs.shape[0]),
            "masked_target_tokens": int(masks.sum()),
            "dialogue_share": float(new_inputs.shape[0] / max(int(inputs.shape[0]), 1)),
            "shards": base._write_shards(tensor_dir / split, inputs, targets, masks),
        }

    tensor_manifest = {
        "schema_version": TENSOR_SCHEMA_VERSION,
        "status": "COMPLETE",
        "objective": {
            "kind": "base_replay_plus_parameterized_dialogue_visibility_response_only",
            "context_length": CONTEXT_LENGTH,
            "loss_mask": "Viv_response_and_end_marker_only",
            "dialogue_context": True,
            "target_coverage": "complete_response_and_end_marker",
            "sampling_policy": f"train_dialogue_chunks_repeated_{oversample}x_validation_once",
        },
        "storage": {
            "dtype": str(STORAGE_DTYPE),
            "loss_mask_dtype": "torch.bool",
            "shard_examples": SHARD_EXAMPLES,
        },
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
        "dialogue_train_oversample": oversample,
        "train_examples": split_manifests["train"]["examples"],
        "validation_examples": split_manifests["validation"]["examples"],
        "dialogue_context_train_examples_unweighted": split_manifests["train"]["dialogue_context_examples_unweighted"],
        "dialogue_context_train_examples": split_manifests["train"]["dialogue_context_examples"],
        "dialogue_context_validation_examples": split_manifests["validation"]["dialogue_context_examples"],
        "dialogue_train_share": split_manifests["train"]["dialogue_share"],
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oversample", type=int, default=1024)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(oversample=args.oversample, source_root=args.source_root, output_dir=args.output_dir)
    print(json.dumps({
        "status": "VIV_SLM_WEIGHTED_DIALOGUE_INPUTS_PASS",
        "output_dir": str(args.output_dir).replace("\\", "/"),
        "source_root": str(args.source_root).replace("\\", "/"),
        "train_examples": manifest["train_examples"],
        "validation_examples": manifest["validation_examples"],
        "dialogue_context_train_examples_unweighted": manifest["dialogue_context_train_examples_unweighted"],
        "dialogue_context_train_examples": manifest["dialogue_context_train_examples"],
        "dialogue_context_validation_examples": manifest["dialogue_context_validation_examples"],
        "dialogue_train_oversample": manifest["dialogue_train_oversample"],
        "dialogue_train_share": manifest["dialogue_train_share"],
        "response_only_loss": manifest["response_only_loss"],
        "world_knowledge_included": manifest["world_knowledge_included"],
        "training_authorized": manifest["training_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
