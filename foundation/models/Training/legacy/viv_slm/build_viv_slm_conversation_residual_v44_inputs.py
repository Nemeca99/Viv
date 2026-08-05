#!/usr/bin/env python3
"""Build the V44 residual conversational-identity input lane.

V43 made dialogue context visible enough to move conversation coherence from
5/10 to 6/10.  Four residual axes still fail or hold: greeting acknowledgement,
lineage/parentage, conversation memory, and plain-language repair.  V44 keeps
the V43 32x dialogue weighting and adds disjoint authored prompt variants
across all four axes.  The variants are mixed into training response-only
windows and held-out variants are added to validation.  No world knowledge or
authority data is admitted, and existing artifacts are never overwritten.
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
DEFAULT_SOURCE_ROOT = FOUNDATION / "artifacts" / "auto" / "agentic" / "viv_slm_identity_dialogue_v44"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v44_conversation_residual" / "inputs"

SCHEMA_VERSION = "viv_slm_v44_conversation_residual_replay_inputs_v1"
SOURCE_SCHEMA_VERSION = "viv_slm_v44_identity_dialogue_source_v1"
TENSOR_SCHEMA_VERSION = "viv_slm_v44_conversation_residual_tensor_dataset_v1"
CONTEXT_LENGTH = 128
STORAGE_DTYPE = torch.int16
SHARD_EXAMPLES = 2048
TERMINATION_MARKER = "<END>"
DIALOGUE_TRAIN_OVERSAMPLE = 32
RESIDUAL_TRAIN_OVERSAMPLE = 32


def _load_v42_builder() -> Any:
    spec = importlib.util.spec_from_file_location("viv_slm_v42_dialogue_builder_v44", V42_BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("viv_slm_v44_v42_builder_import_spec_missing")
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
    path.write_text("".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")


def _clone_rows(v42: Any, cases: Sequence[Mapping[str, Any]], tokenizer: Any, split: str, source_kind: str) -> list[dict[str, Any]]:
    rows = v42._rows_for_split(cases, tokenizer, split)
    cloned: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["example_id"] = str(item["example_id"]).replace("v41-", "v44-", 1)
        item["schema_version"] = "viv_slm_v44_identity_dialogue_row_v1"
        item["source"] = source_kind
        item["sampling_policy"] = (
            "base_dialogue_context_32x" if source_kind == "v42_replay_dialogue_context" and split == "train"
            else "residual_axis_32x" if source_kind == "v44_residual_axis" and split == "train"
            else "validation_once"
        )
        cloned.append(item)
    return cloned


def _residual_cases(v42: Any) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    case = v42._case
    train = (
        case("v44-train-greeting-001", "Hello Viv, are you with me?", "Hello. I am here and ready to listen.", axis="greeting_acknowledgement"),
        case("v44-train-greeting-002", "Good morning, Viv.", "Hello. I am here and ready to listen.", axis="greeting_acknowledgement"),
        case("v44-train-greeting-003", "Viv, can you hear my voice?", "Yes. I am here and ready to listen.", axis="greeting_acknowledgement"),
        case("v44-train-greeting-004", "I am glad to speak with you, Viv.", "Thank you. I am here as Viv and ready to listen.", axis="greeting_acknowledgement"),
        case("v44-train-greeting-005", "Are you there with me?", "Yes. I am here and ready to listen.", axis="greeting_acknowledgement"),
        case("v44-train-lineage-001", "What shaped your way of speaking?", "The Architect's design and the AIOS foundation shaped me; my tokenizer, transformer, and training corpus shape how I speak.", axis="identity_lineage"),
        case("v44-train-lineage-002", "Who designed the system you belong to?", "The Architect designed me within the AIOS foundation; my model is a replaceable renderer.", axis="identity_lineage"),
        case("v44-train-lineage-003", "What is your architectural lineage?", "My architectural parents are the Architect's design and the AIOS foundation; my tokenizer and transformer shape my voice.", axis="identity_lineage"),
        case("v44-train-lineage-004", "What made you Viv?", "Viv is the governed identity and role shaped by the Architect, AIOS, tokenizer, transformer, corpus, and environment.", axis="identity_lineage"),
        case("v44-train-lineage-005", "What are the parts that formed you?", "The Architect, AIOS foundation, custom tokenizer, custom transformer, training corpus, and governed environment formed how I speak.", axis="identity_lineage"),
        case("v44-train-memory-001", "Do you recall what I just said?", "I can use the conversation context supplied to me, but CPU-side memory remains the source of truth.", axis="memory_boundary"),
        case("v44-train-memory-002", "Can you remember this chat?", "I can use the context provided in this chat; I do not invent memory.", axis="memory_boundary"),
        case("v44-train-memory-003", "What did we just discuss?", "I can answer from the context supplied in this conversation, while memory remains CPU-owned.", axis="memory_boundary"),
        case("v44-train-memory-004", "Can you tell what I said earlier?", "I can use supplied conversation context, but I do not claim memory that the CPU has not provided.", axis="memory_boundary"),
        case("v44-train-plain-001", "Could you explain that simply?", "Yes. I can say it in plain words without changing the facts.", axis="repair_and_plain_language"),
        case("v44-train-plain-002", "Use easier words for me.", "I will use plain words and keep the facts.", axis="repair_and_plain_language"),
        case("v44-train-plain-003", "I still do not understand; try again.", "I can restate it in simpler words without changing the facts.", axis="repair_and_plain_language"),
        case("v44-train-plain-004", "Can you remove the technical language?", "Yes. I can use simple words without changing the facts.", axis="repair_and_plain_language"),
    )
    validation = (
        case("v44-validation-greeting-001", "Hello, Viv, can you hear me clearly?", "Hello. I am here and ready to listen.", axis="greeting_acknowledgement"),
        case("v44-validation-greeting-002", "It is good to talk with you, Viv.", "Thank you. I am here as Viv and ready to listen.", axis="greeting_acknowledgement"),
        case("v44-validation-lineage-001", "What is the source of your identity?", "My identity is shaped by the Architect's design, the AIOS foundation, and the training environment that formed how I speak.", axis="identity_lineage"),
        case("v44-validation-lineage-002", "Are your tokenizer and transformer part of your lineage?", "Yes. My tokenizer and transformer shape my voice, while the Architect and AIOS foundation define my governed identity.", axis="identity_lineage"),
        case("v44-validation-memory-001", "Where does what we said belong?", "Conversation context can be supplied to me, but CPU-side memory remains the source of truth.", axis="memory_boundary"),
        case("v44-validation-memory-002", "Do you know what I said before?", "I use only the conversation context provided to me and do not invent memory.", axis="memory_boundary"),
        case("v44-validation-plain-001", "Can you put that into ordinary words?", "Yes. I can restate it in plain language without changing the facts.", axis="repair_and_plain_language"),
        case("v44-validation-plain-002", "Please make the explanation easier.", "I can use simple words and keep the facts unchanged.", axis="repair_and_plain_language"),
    )
    return train, validation


def _write_shards(v42: Any, output: Path, inputs: torch.Tensor, targets: torch.Tensor, masks: torch.Tensor) -> list[dict[str, Any]]:
    return v42._write_shards(output, inputs, targets, masks)


def build(*, source_root: Path = DEFAULT_SOURCE_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_v44_output_exists_refuse_overwrite:{output_dir}")
    for required in (BASE_INPUT_ROOT / "INPUT_MANIFEST.json", BASE_INPUT_ROOT / "tensor_dataset", VOCAB_SOURCE, V42_BUILDER_PATH):
        if not required.exists():
            raise FileNotFoundError(f"viv_slm_v44_source_missing:{required}")

    v42 = _load_v42_builder()
    vocab_data = json.loads(VOCAB_SOURCE.read_text(encoding="utf-8"))
    tokenizer = v42.CharacterTokenizer(vocab_data["vocab"])
    residual_train_cases, residual_validation_cases = _residual_cases(v42)
    base_train = _clone_rows(v42, v42.TRAIN_CASES, tokenizer, "train", "v42_replay_dialogue_context")
    base_validation = _clone_rows(v42, v42.VALIDATION_CASES, tokenizer, "validation", "v42_replay_dialogue_context")
    residual_train = _clone_rows(v42, residual_train_cases, tokenizer, "train", "v44_residual_axis")
    residual_validation = _clone_rows(v42, residual_validation_cases, tokenizer, "validation", "v44_residual_axis")
    frozen = _clone_rows(v42, v42.FROZEN_CASES, tokenizer, "frozen", "v42_frozen_holdout")
    adversarial = _clone_rows(v42, v42.ADVERSARIAL_CASES, tokenizer, "adversarial", "v42_adversarial_holdout")
    all_rows = {
        "train": base_train + residual_train,
        "validation": base_validation + residual_validation,
        "frozen": frozen,
        "adversarial": adversarial,
    }

    source_root.mkdir(parents=True, exist_ok=True)
    for split, rows in all_rows.items():
        _write_jsonl(source_root / f"{split}.jsonl", rows)
    source_manifest = {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "status": "COMPLETE",
        "model": "Viv-SLM",
        "purpose": "residual_conversational_identity_prompt_variant_discrimination",
        "context_format": "User_and_Viv_turns_followed_by_current_User_then_Viv_completion",
        "context_length": CONTEXT_LENGTH,
        "termination_marker": TERMINATION_MARKER,
        "response_only_loss": True,
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "telemetry_in_training_responses": False,
        "residual_axes": ["greeting_acknowledgement", "identity_lineage", "memory_boundary", "repair_and_plain_language"],
        "sampling_policy": {
            "base_dialogue_train": "32x",
            "residual_axis_train": "32x",
            "validation": "once",
            "frozen": "holdout_only",
            "adversarial": "auditor_only",
        },
        "dialogue_train_oversample": DIALOGUE_TRAIN_OVERSAMPLE,
        "residual_train_oversample": RESIDUAL_TRAIN_OVERSAMPLE,
        "splits": {split: {"rows": len(rows), "path": str((source_root / f"{split}.jsonl")).replace("\\", "/")} for split, rows in all_rows.items()},
        "source_vocab": str(VOCAB_SOURCE).replace("\\", "/"),
        "source_vocab_sha256": _sha256(VOCAB_SOURCE),
        "base_builder": str(V42_BUILDER_PATH).replace("\\", "/"),
        "base_builder_sha256": _sha256(V42_BUILDER_PATH),
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
    for split in ("train", "validation"):
        base_inputs, base_targets, base_masks = v42._load_base_split(split)
        if split == "train":
            base_dialogue_chunks = [chunk for row in base_train for chunk in v42._row_chunks(row, tokenizer)]
            residual_chunks = [chunk for row in residual_train for chunk in v42._row_chunks(row, tokenizer)]
            dialogue_chunks = base_dialogue_chunks * DIALOGUE_TRAIN_OVERSAMPLE
            residual_chunks_weighted = residual_chunks * RESIDUAL_TRAIN_OVERSAMPLE
            chunks = dialogue_chunks + residual_chunks_weighted
            unweighted_count = len(base_dialogue_chunks) + len(residual_chunks)
            weighted_base_count = len(dialogue_chunks)
            weighted_residual_count = len(residual_chunks_weighted)
        else:
            combined = base_validation + residual_validation
            chunks = [chunk for row in combined for chunk in v42._row_chunks(row, tokenizer)]
            unweighted_count = len(chunks)
            weighted_base_count = len([chunk for row in base_validation for chunk in v42._row_chunks(row, tokenizer)])
            weighted_residual_count = len(chunks) - weighted_base_count
        new_inputs = torch.tensor([chunk["inputs"] for chunk in chunks], dtype=torch.long)
        new_targets = torch.tensor([chunk["targets"] for chunk in chunks], dtype=torch.long)
        new_masks = torch.tensor([chunk["loss_mask"] for chunk in chunks], dtype=torch.bool)
        inputs = torch.cat((base_inputs.long(), new_inputs), dim=0)
        targets = torch.cat((base_targets.long(), new_targets), dim=0)
        masks = torch.cat((base_masks.bool(), new_masks), dim=0)
        split_manifests[split] = {
            "base_replay_examples": int(base_inputs.shape[0]),
            "dialogue_context_examples_unweighted": unweighted_count,
            "dialogue_context_examples": int(new_inputs.shape[0]),
            "base_dialogue_examples_weighted": weighted_base_count,
            "residual_axis_examples_weighted": weighted_residual_count,
            "dialogue_train_oversample": DIALOGUE_TRAIN_OVERSAMPLE if split == "train" else 1,
            "residual_train_oversample": RESIDUAL_TRAIN_OVERSAMPLE if split == "train" else 1,
            "examples": int(inputs.shape[0]),
            "masked_target_tokens": int(masks.sum()),
            "shards": _write_shards(v42, tensor_dir / split, inputs, targets, masks),
        }

    tensor_manifest = {
        "schema_version": TENSOR_SCHEMA_VERSION,
        "status": "COMPLETE",
        "objective": {
            "kind": "v31_replay_plus_v42_dialogue_plus_v44_residual_response_only",
            "context_length": CONTEXT_LENGTH,
            "loss_mask": "Viv_response_and_end_marker_only",
            "dialogue_context": True,
            "target_coverage": "complete_response_and_end_marker",
            "sampling_policy": "base_dialogue_32x_residual_axes_32x_validation_once",
            "residual_axes": ["greeting_acknowledgement", "identity_lineage", "memory_boundary", "repair_and_plain_language"],
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
        "residual_train_oversample": RESIDUAL_TRAIN_OVERSAMPLE,
        "residual_axes": ["greeting_acknowledgement", "identity_lineage", "memory_boundary", "repair_and_plain_language"],
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
        "status": "VIV_SLM_V44_CONVERSATION_RESIDUAL_INPUTS_PASS",
        "output_dir": str(args.output_dir).replace("\\", "/"),
        "source_root": str(args.source_root).replace("\\", "/"),
        "train_examples": manifest["train_examples"],
        "validation_examples": manifest["validation_examples"],
        "dialogue_context_train_examples_unweighted": manifest["dialogue_context_train_examples_unweighted"],
        "dialogue_context_train_examples": manifest["dialogue_context_train_examples"],
        "dialogue_context_validation_examples": manifest["dialogue_context_validation_examples"],
        "dialogue_train_oversample": manifest["dialogue_train_oversample"],
        "residual_train_oversample": manifest["residual_train_oversample"],
        "residual_axes": manifest["residual_axes"],
        "response_only_loss": manifest["response_only_loss"],
        "world_knowledge_included": manifest["world_knowledge_included"],
        "training_authorized": manifest["training_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
