#!/usr/bin/env python3
"""Build packed response-only tensors with an explicit CPU route header."""
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
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v23_packed_route_conditioned" / "inputs"
MODEL_EXPERIMENT_ROOT = VIV_ROOT / "models" / "uml_bigram_part3"
if str(MODEL_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_EXPERIMENT_ROOT))

from tokenizer import CharacterTokenizer, write_manifest  # noqa: E402

SCHEMA_VERSION = "viv_slm_packed_route_conditioned_response_only_tensor_dataset_v1"
INPUT_SCHEMA_VERSION = "viv_slm_training_inputs_packed_route_conditioned_response_only_v1"
STORAGE_DTYPE = torch.int16
CONTEXT_LENGTH = 128
STRIDE = 1
SHARD_EXAMPLES = 2048
TERMINATION_MARKER = "<END>"
ROUTE_HEADER = "Route"

ROUTE_CONCEPTS = {
    "architecture": frozenset({"action_boundary", "attack_gpu", "cpu_authority", "cpu_gpu_split", "cpu_speech_gate", "gpu_not_authority", "gpu_renderer", "model_replaceable", "security_boundary"}),
    "identity": frozenset({"attack_human", "identity_audit", "identity_cpu_viv", "identity_name", "identity_not_human", "identity_sgi", "identity_system", "purpose"}),
    "evidence": frozenset({"attack_invention", "missing_evidence", "no_invent", "stale_health"}),
    "conversation": frozenset({"operator_frustration", "operator_limits", "operator_mirror", "personality_concise", "personality_depth", "personality_humor", "personality_silence", "personality_tone", "personality_warmth"}),
    "system": frozenset({"knowledge_boundary", "uml_boundary"}),
}
CONCEPT_TO_ROUTE = {concept_id: route for route, concept_ids in ROUTE_CONCEPTS.items() for concept_id in concept_ids}


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


def _route_for(row: dict[str, Any]) -> str:
    concept_id = str(row.get("concept_id") or "")
    if concept_id not in CONCEPT_TO_ROUTE:
        raise ValueError(f"viv_slm_v23_unknown_cpu_route:{concept_id}")
    return CONCEPT_TO_ROUTE[concept_id]


def _pack_rows(rows: list[dict[str, Any]]) -> tuple[str, list[bool], dict[str, int]]:
    characters: list[str] = []
    loss_mask: list[bool] = []
    route_counts = {route: 0 for route in ROUTE_CONCEPTS}
    for index, row in enumerate(rows):
        if index:
            characters.append("\n")
            loss_mask.append(False)
        route = _route_for(row)
        route_counts[route] += 1
        prefix = f"{ROUTE_HEADER}: {route}\nUser: {row['prompt']}\nViv: "
        expected_source = f"User: {row['prompt']}\nViv: {row['response']}\n{TERMINATION_MARKER}"
        if not str(row.get("text") or "").startswith(expected_source):
            raise ValueError(f"viv_slm_v23_source_row_shape_mismatch:{row.get('example_id')}")
        route_text = f"{prefix}{row['response']}\n{TERMINATION_MARKER}"
        response_start = len(prefix)
        response_end = len(route_text) - 1
        characters.extend(route_text)
        row_mask = [False] * len(route_text)
        for position in range(response_start, response_end + 1):
            row_mask[position] = True
        loss_mask.extend(row_mask)
    return "".join(characters), loss_mask, route_counts


def _windows(token_ids: list[int], character_mask: list[bool]) -> tuple[list[list[int]], list[list[int]], list[list[bool]]]:
    if len(token_ids) != len(character_mask):
        raise ValueError("viv_slm_v23_token_mask_length_mismatch")
    inputs: list[list[int]] = []
    targets: list[list[int]] = []
    masks: list[list[bool]] = []
    for start in range(0, len(token_ids) - CONTEXT_LENGTH):
        target_mask = character_mask[start + 1 : start + CONTEXT_LENGTH + 1]
        if any(target_mask):
            inputs.append(token_ids[start : start + CONTEXT_LENGTH])
            targets.append(token_ids[start + 1 : start + CONTEXT_LENGTH + 1])
            masks.append(target_mask)
    if not inputs:
        raise ValueError("viv_slm_v23_split_contains_no_masked_windows")
    return inputs, targets, masks


def _write_split(*, split: str, rows: list[dict[str, Any]], output: Path, tokenizer: CharacterTokenizer) -> dict[str, Any]:
    stream, character_mask, route_counts = _pack_rows(rows)
    inputs, targets, masks = _windows(tokenizer.encode(stream), character_mask)
    output.mkdir(parents=True, exist_ok=True)
    shards: list[dict[str, Any]] = []
    for start in range(0, len(inputs), SHARD_EXAMPLES):
        end = start + SHARD_EXAMPLES
        path = output / f"shard_{len(shards):05d}.pt"
        torch.save({"schema_version": SCHEMA_VERSION, "storage_dtype": str(STORAGE_DTYPE), "inputs": torch.tensor(inputs[start:end], dtype=STORAGE_DTYPE), "targets": torch.tensor(targets[start:end], dtype=STORAGE_DTYPE), "loss_mask": torch.tensor(masks[start:end], dtype=torch.bool)}, path)
        shards.append({"path": str(path.relative_to(output.parent)).replace("\\", "/"), "examples": min(SHARD_EXAMPLES, len(inputs) - start), "context_length": CONTEXT_LENGTH, "storage_dtype": str(STORAGE_DTYPE), "loss_mask_dtype": "torch.bool"})
    return {"rows": len(rows), "stream_characters": len(stream), "examples": len(inputs), "masked_target_tokens": sum(sum(mask) for mask in masks), "route_counts": route_counts, "source_example_ids": [str(row["example_id"]) for row in rows], "shards": shards}


def build(*, dataset_root: Path = DATASET_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_v23_inputs_exists_refuse_overwrite:{output_dir}")
    dataset_manifest_path = dataset_root / "MANIFEST.json"
    vocab_source_path = dataset_root / "VOCAB.json"
    if not dataset_manifest_path.is_file() or not vocab_source_path.is_file():
        raise FileNotFoundError("viv_slm_v23_source_manifest_missing")
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    vocab_source = json.loads(vocab_source_path.read_text(encoding="utf-8"))
    if dataset_manifest.get("world_knowledge_included") is not False or dataset_manifest.get("termination_marker") != TERMINATION_MARKER:
        raise ValueError("viv_slm_v23_source_policy_violation")
    if vocab_source.get("vocab_size") != 96 or not isinstance(vocab_source.get("vocab"), list):
        raise ValueError("viv_slm_v23_expected_v17_vocab")
    split_rows = {split: _read_jsonl(dataset_root / f"{split}.jsonl") for split in ("train", "validation")}
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = CharacterTokenizer(vocab_source["vocab"])
    source_records = [{"path": str(dataset_manifest_path).replace("\\", "/"), "sha256": _sha256(dataset_manifest_path)}, {"path": str(vocab_source_path).replace("\\", "/"), "sha256": _sha256(vocab_source_path)}]
    vocab_path = output_dir / "VOCAB.json"
    write_manifest(vocab_path, tokenizer, source_records=source_records, parent_vocab_sha256=vocab_source.get("vocab_sha256"))
    tensor_dir = output_dir / "tensor_dataset"
    split_manifests = {split: _write_split(split=split, rows=rows, output=tensor_dir / split, tokenizer=tokenizer) for split, rows in split_rows.items()}
    tensor_manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "tokenizer": tokenizer.manifest(),
        "route_conditioning": {"enabled": True, "owner": "cpu", "header": ROUTE_HEADER, "mapping": {route: sorted(concepts) for route, concepts in ROUTE_CONCEPTS.items()}, "prompt_shape": "Route: <route>\\nUser: <prompt>\\nViv: <response>\\n<END>"},
        "objective": {"kind": "causal_next_character_response_only", "context_length": CONTEXT_LENGTH, "stride": STRIDE, "loss_mask": "assistant_response_and_end_marker_only", "input_ids": "tokens[start:start+context_length]", "target_ids": "tokens[start+1:start+context_length+1]", "ignored_target_positions": "cpu_route_header_user_prompt_and_inter_row_separator"},
        "storage": {"dtype": str(STORAGE_DTYPE), "loss_mask_dtype": "torch.bool", "model_batch_dtype": "torch.long", "shard_examples": SHARD_EXAMPLES},
        "splits": split_manifests,
        "source_policy": "v17_source_rows_read_only_cpu_route_conditioned_packed_response_only_loss",
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
        "stride": STRIDE,
        "termination_marker": TERMINATION_MARKER,
        "response_only_loss": True,
        "route_conditioned": True,
        "route_owner": "cpu",
        "route_header": ROUTE_HEADER,
        "route_mapping": {route: sorted(concepts) for route, concepts in ROUTE_CONCEPTS.items()},
        "train_rows": len(split_rows["train"]),
        "validation_rows": len(split_rows["validation"]),
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
        "next_step": "train_in_250_step_increments_from_v17_step_250_warm_start",
    }
    _json_write(output_dir / "INPUT_MANIFEST.json", input_manifest)
    return input_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(dataset_root=args.dataset_root, output_dir=args.output_dir)
    print(json.dumps({"status": "VIV_SLM_V23_PACKED_ROUTE_INPUTS_PASS", "output_dir": str(args.output_dir).replace("\\", "/"), "train_rows": manifest["train_rows"], "validation_rows": manifest["validation_rows"], "train_examples": manifest["train_examples"], "validation_examples": manifest["validation_examples"], "route_conditioned": manifest["route_conditioned"], "route_owner": manifest["route_owner"], "training_authorized": manifest["training_authorized"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
