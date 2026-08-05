#!/usr/bin/env python3
"""Build the canonical V60 identity retention/replay input package.

The builder is preparation-only.  It never opens training authority, touches
checkpoints, changes the live model, or admits knowledge data.  It combines
the canonical V43 identity/conversation train split with a deterministic,
train-only sample from the V16 response-only identity split.  V43 validation
is copied as the sole validation surface; V16 validation is intentionally not
read or copied.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping

import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from paths import TRAINING_ROOT, VIV_SLM_ROOT, viv_path  # noqa: E402


MASKED_SCHEMA = "viv_slm_response_only_tensor_dataset_v1"
CONTEXT_LENGTH = 128
VOCAB_SIZE = 96


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"viv_slm_v60_json_object_required:{path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"viv_slm_v60_output_exists_refuse_overwrite:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _canonical(path: Path) -> str:
    return str(path).replace("\\", "/")


def _require_closed_authority(record: Mapping[str, Any], *, source: str) -> None:
    required_fields = ("training_authorized", "run_authorized", "promotion_authorized")
    optional_fields = (
        "deployment_authorized",
        "deployment_changed",
        "live_model_changed",
        "global_aifl_writes",
        "master_s_n_mutation",
        "knowledge_admission",
    )
    for field in required_fields:
        if record.get(field) is not False:
            raise PermissionError(f"viv_slm_v60_authority_not_closed:{source}:{field}")
    for field in optional_fields:
        if field in record and record[field] is not False:
            raise PermissionError(f"viv_slm_v60_authority_not_closed:{source}:{field}")


def _require_closed_knob_authority(record: Mapping[str, Any]) -> None:
    """Validate the registry's authority shape without inventing missing fields."""

    for field in (
        "this_file_opens_authority",
        "training_authorized",
        "run_authorized",
        "promotion_authorized",
        "deployment_authorized",
        "live_model_mutation",
        "global_aifl_writes",
        "master_s_n_mutation",
        "knowledge_admission",
    ):
        if record.get(field) is not False:
            raise PermissionError(f"viv_slm_v60_knob_authority_not_closed:{field}")


def _load_vocab(path: Path) -> tuple[dict[str, Any], str]:
    value = _read_json(path)
    vocab = value.get("vocab")
    if not isinstance(vocab, list) or len(vocab) != VOCAB_SIZE:
        raise ValueError(f"viv_slm_v60_vocab_invalid:{path}")
    if value.get("vocab_size") != VOCAB_SIZE:
        raise ValueError(f"viv_slm_v60_vocab_size_invalid:{path}")
    return value, _sha256(path)


def _manifest_contract(root: Path, *, label: str) -> dict[str, Any]:
    input_manifest_path = root / "INPUT_MANIFEST.json"
    tensor_manifest_path = root / "tensor_dataset" / "MANIFEST.json"
    vocab_path = root / "VOCAB.json"
    for path in (input_manifest_path, tensor_manifest_path, vocab_path):
        if not path.is_file():
            raise FileNotFoundError(f"viv_slm_v60_dataset_file_missing:{label}:{path}")
    input_manifest = _read_json(input_manifest_path)
    tensor_manifest = _read_json(tensor_manifest_path)
    vocab, vocab_sha256 = _load_vocab(vocab_path)
    _require_closed_authority(input_manifest, source=label)
    if input_manifest.get("response_only_loss") is not True:
        raise ValueError(f"viv_slm_v60_response_only_required:{label}")
    if input_manifest.get("world_knowledge_included") is not False:
        raise ValueError(f"viv_slm_v60_world_knowledge_forbidden:{label}")
    if input_manifest.get("context_length") != CONTEXT_LENGTH:
        raise ValueError(f"viv_slm_v60_context_length_mismatch:{label}")
    if input_manifest.get("vocab_size") != VOCAB_SIZE:
        raise ValueError(f"viv_slm_v60_manifest_vocab_size_mismatch:{label}")
    return {
        "label": label,
        "root": root,
        "input_manifest_path": input_manifest_path,
        "input_manifest": input_manifest,
        "input_manifest_sha256": _sha256(input_manifest_path),
        "tensor_manifest_path": tensor_manifest_path,
        "tensor_manifest": tensor_manifest,
        "tensor_manifest_sha256": _sha256(tensor_manifest_path),
        "vocab_path": vocab_path,
        "vocab": vocab,
        "vocab_sha256": vocab_sha256,
    }


def _load_split(root: Path, split: str, *, label: str) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, list[Path]]:
    paths = sorted((root / "tensor_dataset" / split).glob("shard_*.pt"))
    if not paths:
        raise FileNotFoundError(f"viv_slm_v60_tensor_shards_missing:{label}:{split}")
    inputs: list[torch.Tensor] = []
    targets: list[torch.Tensor] = []
    masks: list[torch.Tensor] = []
    for path in paths:
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if not isinstance(payload, dict) or payload.get("schema_version") != MASKED_SCHEMA:
            raise ValueError(f"viv_slm_v60_tensor_schema_mismatch:{label}:{path}")
        split_inputs = payload.get("inputs")
        split_targets = payload.get("targets")
        split_masks = payload.get("loss_mask")
        if not all(isinstance(value, torch.Tensor) for value in (split_inputs, split_targets, split_masks)):
            raise ValueError(f"viv_slm_v60_tensor_payload_missing:{label}:{path}")
        if split_inputs.ndim != 2 or split_inputs.shape != split_targets.shape or split_masks.shape != split_inputs.shape:
            raise ValueError(f"viv_slm_v60_tensor_shape_mismatch:{label}:{path}")
        if split_inputs.shape[1] != CONTEXT_LENGTH or split_masks.dtype is not torch.bool:
            raise ValueError(f"viv_slm_v60_tensor_contract_mismatch:{label}:{path}")
        if split_inputs.numel() and (
            int(split_inputs.min()) < 0
            or int(split_inputs.max()) >= VOCAB_SIZE
            or int(split_targets.min()) < 0
            or int(split_targets.max()) >= VOCAB_SIZE
        ):
            raise ValueError(f"viv_slm_v60_tensor_token_range_mismatch:{label}:{path}")
        if not bool(split_masks.any(dim=1).all()):
            raise ValueError(f"viv_slm_v60_empty_response_mask:{label}:{path}")
        inputs.append(split_inputs.to(dtype=torch.int16).contiguous())
        targets.append(split_targets.to(dtype=torch.int16).contiguous())
        masks.append(split_masks.to(dtype=torch.bool).contiguous())
    return torch.cat(inputs, dim=0), torch.cat(targets, dim=0), torch.cat(masks, dim=0), paths


def _shard_records(root: Path, split: str, count: int, mask_tokens: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((root / "tensor_dataset" / split).glob("shard_*.pt")):
        payload = torch.load(path, map_location="cpu", weights_only=True)
        inputs = payload["inputs"]
        masks = payload["loss_mask"]
        records.append(
            {
                "path": f"{split}/{path.name}",
                "examples": int(inputs.shape[0]),
                "context_length": int(inputs.shape[1]),
                "storage_dtype": str(inputs.dtype).replace("torch.", "torch."),
                "loss_mask_dtype": str(masks.dtype).replace("torch.", "torch."),
                "sha256": _sha256(path),
            }
        )
    if sum(int(record["examples"]) for record in records) != count:
        raise ValueError(f"viv_slm_v60_shard_manifest_count_mismatch:{split}")
    if split == "train" and sum(
        int(torch.load(root / "tensor_dataset" / record["path"], map_location="cpu", weights_only=True)["loss_mask"].sum())
        for record in records
    ) != mask_tokens:
        raise ValueError("viv_slm_v60_shard_manifest_mask_count_mismatch:train")
    return records


def load_configuration() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path, Path, Path, float, int, int]:
    knob_path = TRAINING_ROOT / "current" / "TRAINING_KNOBS.json"
    knob_registry = _read_json(knob_path)
    _require_closed_knob_authority(knob_registry.get("authority", {}))
    identity = knob_registry.get("identity_data")
    if not isinstance(identity, Mapping):
        raise ValueError("viv_slm_v60_identity_data_knobs_missing")
    index_path = viv_path(str(identity.get("index") or ""))
    identity_index = _read_json(index_path)
    policy = identity_index.get("policy")
    if not isinstance(policy, Mapping) or policy.get("identity_before_knowledge") is not True or policy.get("knowledge_admission_for_v60") is not False:
        raise PermissionError("viv_slm_v60_identity_first_policy_invalid")
    use = identity_index.get("v60_use")
    if not isinstance(use, Mapping) or use.get("knowledge_root") is not None:
        raise PermissionError("viv_slm_v60_knowledge_admission_invalid")
    base_root = viv_path(str(use.get("input_root") or ""))
    retention_root = viv_path(str(use.get("retention_root") or ""))
    output_root = viv_path(str(use.get("prepared_root") or identity.get("prepared_v60_dataset") or ""))
    if _canonical(base_root) != _canonical(viv_path(str(identity.get("base_dataset") or ""))):
        raise ValueError("viv_slm_v60_base_root_knob_index_mismatch")
    if _canonical(retention_root) != _canonical(viv_path(str(identity.get("retention_dataset") or ""))):
        raise ValueError("viv_slm_v60_retention_root_knob_index_mismatch")
    fraction = float(identity.get("retention_fraction_of_base_train"))
    seed = int(identity.get("retention_sampling_seed"))
    shard_size = int(identity.get("max_shard_examples"))
    if not 0.0 < fraction <= 1.0 or seed < 0 or shard_size <= 0:
        raise ValueError("viv_slm_v60_identity_data_knob_bounds_invalid")
    base = _manifest_contract(base_root, label="v43_conversation_focus")
    retention = _manifest_contract(retention_root, label="v16_response_only")
    pinned_hashes = {
        "index_sha256": _sha256(index_path),
        "base_input_manifest_sha256": base["input_manifest_sha256"],
        "base_tensor_manifest_sha256": base["tensor_manifest_sha256"],
        "retention_input_manifest_sha256": retention["input_manifest_sha256"],
        "retention_tensor_manifest_sha256": retention["tensor_manifest_sha256"],
    }
    for field, actual in pinned_hashes.items():
        expected = str(identity.get(field) or "")
        if expected and expected.casefold() != actual.casefold():
            raise ValueError(f"viv_slm_v60_identity_data_hash_mismatch:{field}:{actual}")
    if base["vocab"] .get("vocab") != retention["vocab"].get("vocab"):
        raise ValueError("viv_slm_v60_vocab_content_mismatch")
    if base["input_manifest"].get("termination_marker") != retention["input_manifest"].get("termination_marker"):
        raise ValueError("viv_slm_v60_termination_marker_mismatch")
    return knob_registry, identity_index, identity, base_root, retention_root, output_root, fraction, seed, shard_size


def build_plan() -> dict[str, Any]:
    knob_registry, identity_index, identity, base_root, retention_root, output_root, fraction, seed, shard_size = load_configuration()
    base_manifest = _read_json(base_root / "INPUT_MANIFEST.json")
    retention_manifest = _read_json(retention_root / "INPUT_MANIFEST.json")
    base_count = int(base_manifest["train_examples"])
    retention_available = int(retention_manifest["train_examples"])
    retention_count = int(round(base_count * fraction))
    if retention_count <= 0 or retention_count > retention_available:
        raise ValueError("viv_slm_v60_retention_count_invalid")
    return {
        "status": "DRY_RUN_READY",
        "builder": _canonical(VIV_SLM_ROOT / Path(__file__).name),
        "knob_registry": {
            "path": _canonical(TRAINING_ROOT / "current" / "TRAINING_KNOBS.json"),
            "sha256": _sha256(TRAINING_ROOT / "current" / "TRAINING_KNOBS.json"),
        },
        "identity_index": {
            "path": _canonical(viv_path(str(identity.get("index")))),
            "sha256": _sha256(viv_path(str(identity.get("index")))),
            "identity_before_knowledge": identity_index["policy"]["identity_before_knowledge"],
            "knowledge_admission": identity_index["policy"]["knowledge_admission_for_v60"],
        },
        "base": {
            "name": "v43_conversation_focus",
            "root": _canonical(base_root),
            "train_examples": base_count,
            "validation_examples": int(base_manifest["validation_examples"]),
            "input_manifest_sha256": _sha256(base_root / "INPUT_MANIFEST.json"),
            "tensor_manifest_sha256": _sha256(base_root / "tensor_dataset" / "MANIFEST.json"),
        },
        "retention": {
            "name": "v16_response_only",
            "root": _canonical(retention_root),
            "source_train_examples": retention_available,
            "selected_train_examples": retention_count,
            "validation_examples_excluded": int(retention_manifest["validation_examples"]),
            "input_manifest_sha256": _sha256(retention_root / "INPUT_MANIFEST.json"),
            "tensor_manifest_sha256": _sha256(retention_root / "tensor_dataset" / "MANIFEST.json"),
        },
        "output": {
            "root": _canonical(output_root),
            "train_examples": base_count + retention_count,
            "validation_source": _canonical(base_root),
            "retention_fraction_of_base_train": fraction,
            "sampling_seed": seed,
            "max_shard_examples": shard_size,
        },
        "authority": {
            "training_authorized": False,
            "run_authorized": False,
            "knowledge_admission": False,
            "writes_live_model": False,
        },
    }


def build(output_root: Path | None = None) -> dict[str, Any]:
    _, identity_index, identity, base_root, retention_root, configured_output, fraction, seed, shard_size = load_configuration()
    output_root = output_root or configured_output
    if output_root.exists():
        raise FileExistsError(f"viv_slm_v60_output_exists_refuse_overwrite:{output_root}")
    base = _manifest_contract(base_root, label="v43_conversation_focus")
    retention = _manifest_contract(retention_root, label="v16_response_only")
    if base["vocab"] .get("vocab") != retention["vocab"].get("vocab"):
        raise ValueError("viv_slm_v60_vocab_content_mismatch")

    base_train, base_targets, base_masks, _ = _load_split(base_root, "train", label="v43_conversation_focus")
    base_validation, base_validation_targets, base_validation_masks, _ = _load_split(base_root, "validation", label="v43_conversation_focus")
    retention_train, retention_targets, retention_masks, _ = _load_split(retention_root, "train", label="v16_response_only")
    selected_count = int(round(base_train.shape[0] * fraction))
    if selected_count <= 0 or selected_count > retention_train.shape[0]:
        raise ValueError("viv_slm_v60_retention_count_invalid")
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    selected_indices = torch.randperm(retention_train.shape[0], generator=generator)[:selected_count]
    selected_indices = torch.sort(selected_indices).values
    selected_train = retention_train[selected_indices]
    selected_targets = retention_targets[selected_indices]
    selected_masks = retention_masks[selected_indices]
    train_inputs = torch.cat((base_train, selected_train), dim=0).contiguous()
    train_targets = torch.cat((base_targets, selected_targets), dim=0).contiguous()
    train_masks = torch.cat((base_masks, selected_masks), dim=0).contiguous()

    build_root = output_root.parent / f".{output_root.name}.__building__"
    if build_root.exists():
        raise FileExistsError(f"viv_slm_v60_build_staging_exists_refuse_overwrite:{build_root}")
    (build_root / "tensor_dataset" / "train").mkdir(parents=True)
    (build_root / "tensor_dataset" / "validation").mkdir(parents=True)
    shutil.copy2(base["vocab_path"], build_root / "VOCAB.json")

    train_records: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, train_inputs.shape[0], shard_size)):
        stop = min(start + shard_size, train_inputs.shape[0])
        path = build_root / "tensor_dataset" / "train" / f"shard_{index:05d}.pt"
        payload = {
            "schema_version": MASKED_SCHEMA,
            "storage_dtype": "torch.int16",
            "loss_mask_dtype": "torch.bool",
            "inputs": train_inputs[start:stop].to(dtype=torch.int16).contiguous(),
            "targets": train_targets[start:stop].to(dtype=torch.int16).contiguous(),
            "loss_mask": train_masks[start:stop].to(dtype=torch.bool).contiguous(),
        }
        torch.save(payload, path)
        train_records.append(
            {
                "path": f"train/{path.name}",
                "examples": stop - start,
                "context_length": CONTEXT_LENGTH,
                "storage_dtype": "torch.int16",
                "loss_mask_dtype": "torch.bool",
                "masked_target_tokens": int(payload["loss_mask"].sum()),
                "sha256": _sha256(path),
            }
        )

    validation_records: list[dict[str, Any]] = []
    for index, source in enumerate(sorted((base_root / "tensor_dataset" / "validation").glob("shard_*.pt"))):
        destination = build_root / "tensor_dataset" / "validation" / f"shard_{index:05d}.pt"
        shutil.copy2(source, destination)
        payload = torch.load(destination, map_location="cpu", weights_only=True)
        validation_records.append(
            {
                "path": f"validation/{destination.name}",
                "examples": int(payload["inputs"].shape[0]),
                "context_length": CONTEXT_LENGTH,
                "storage_dtype": "torch.int16",
                "loss_mask_dtype": "torch.bool",
                "masked_target_tokens": int(payload["loss_mask"].sum()),
                "sha256": _sha256(destination),
            }
        )

    tensor_manifest = {
        "schema_version": "viv_slm_v60_preservation_replay_tensor_dataset_v1",
        "source_policy": "v43_train_plus_deterministic_v16_train_only_response_only_replay; v43_validation_only",
        "objective": {
            "kind": "v60_v43_base_plus_v16_identity_retention_response_only",
            "context_length": CONTEXT_LENGTH,
            "loss_mask": "Viv_response_and_end_marker_only",
            "validation_source": "v43_conversation_focus",
            "v16_validation_in_training": False,
        },
        "sources": {
            "base": {
                "root": _canonical(base_root),
                "input_manifest_sha256": base["input_manifest_sha256"],
                "tensor_manifest_sha256": base["tensor_manifest_sha256"],
                "train_examples_used": int(base_train.shape[0]),
            },
            "retention": {
                "root": _canonical(retention_root),
                "input_manifest_sha256": retention["input_manifest_sha256"],
                "tensor_manifest_sha256": retention["tensor_manifest_sha256"],
                "source_train_examples": int(retention_train.shape[0]),
                "selected_train_examples": selected_count,
                "sampling_seed": seed,
                "sampling_algorithm": "torch.randperm_cpu_sorted_indices",
                "validation_examples_excluded": int(retention["input_manifest"].get("validation_examples") or 0),
            },
        },
        "splits": {
            "train": {
                "examples": int(train_inputs.shape[0]),
                "base_examples": int(base_train.shape[0]),
                "retention_examples": selected_count,
                "masked_target_tokens": int(train_masks.sum()),
                "shards": train_records,
            },
            "validation": {
                "examples": int(base_validation.shape[0]),
                "source": "v43_conversation_focus",
                "masked_target_tokens": int(base_validation_masks.sum()),
                "shards": validation_records,
            },
        },
    }
    _write_json(build_root / "tensor_dataset" / "MANIFEST.json", tensor_manifest)

    input_manifest = {
        "schema_version": "viv_slm_v60_preservation_replay_inputs_v1",
        "status": "COMPLETE_TRAINING_CLOSED",
        "model": "Viv-SLM",
        "context_length": CONTEXT_LENGTH,
        "vocab_size": VOCAB_SIZE,
        "vocab_manifest": _canonical(output_root / "VOCAB.json"),
        "vocab_manifest_sha256": _sha256(build_root / "VOCAB.json"),
        "tensor_manifest": _canonical(output_root / "tensor_dataset" / "MANIFEST.json"),
        "tensor_manifest_sha256": _sha256(build_root / "tensor_dataset" / "MANIFEST.json"),
        "termination_marker": base["input_manifest"].get("termination_marker"),
        "response_only_loss": True,
        "world_knowledge_included": False,
        "base_dataset": {
            "name": "v43_conversation_focus",
            "root": _canonical(base_root),
            "input_manifest_sha256": base["input_manifest_sha256"],
            "tensor_manifest_sha256": base["tensor_manifest_sha256"],
        },
        "retention_dataset": {
            "name": "v16_response_only",
            "root": _canonical(retention_root),
            "input_manifest_sha256": retention["input_manifest_sha256"],
            "tensor_manifest_sha256": retention["tensor_manifest_sha256"],
            "train_only": True,
            "selected_train_examples": selected_count,
            "sampling_seed": seed,
            "validation_excluded": True,
        },
        "train_examples": int(train_inputs.shape[0]),
        "validation_examples": int(base_validation.shape[0]),
        "validation_source": "v43_conversation_focus_only",
        "identity_before_knowledge": True,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
        "deployment_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "global_aifl_writes": False,
        "master_s_n_mutation": False,
        "knowledge_admission": False,
    }
    _write_json(build_root / "INPUT_MANIFEST.json", input_manifest)
    build_root.rename(output_root)
    return {
        "status": "BUILT_HASH_VERIFIED",
        "output_root": _canonical(output_root),
        "input_manifest_sha256": _sha256(output_root / "INPUT_MANIFEST.json"),
        "tensor_manifest_sha256": _sha256(output_root / "tensor_dataset" / "MANIFEST.json"),
        "vocab_sha256": _sha256(output_root / "VOCAB.json"),
        "train_examples": int(train_inputs.shape[0]),
        "validation_examples": int(base_validation.shape[0]),
        "base_examples": int(base_train.shape[0]),
        "retention_examples": selected_count,
        "retention_fraction_of_base_train": fraction,
        "sampling_seed": seed,
        "validation_source": "v43_conversation_focus_only",
        "v16_validation_in_training": False,
        "authority": {
            "training_authorized": False,
            "run_authorized": False,
            "knowledge_admission": False,
            "live_model_changed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate the declarative data contract without writing tensors.")
    parser.add_argument("--build", action="store_true", help="Build the new canonical V60 input package.")
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args()
    if args.dry_run == args.build:
        parser.error("choose exactly one of --dry-run or --build")
    result = build_plan() if args.dry_run else build(args.output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
