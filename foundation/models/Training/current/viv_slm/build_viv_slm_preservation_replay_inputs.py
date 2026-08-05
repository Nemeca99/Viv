#!/usr/bin/env python3
"""Build a declarative identity preservation/replay input package.

The builder is preparation-only.  A lane is selected from the central
``TRAINING_KNOBS.json`` registry, then its base and retention datasets are
hash-checked before a deterministic train-only mixture is prepared.  The
builder never opens training authority, reads retention validation tensors,
touches checkpoints, changes the live model, admits knowledge, or overwrites
an existing package.

V60 remains a frozen executable specification.  This generic builder is the
current path for future identity preservation lanes so a new experiment can
change a declarative lane value instead of copying another version-specific
trainer.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping

import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from paths import TRAINING_ROOT, VIV_SLM_ROOT, viv_path  # noqa: E402
import build_viv_slm_v60_preservation_replay_inputs as core  # noqa: E402


DEFAULT_LANE_ID = "v61_stratified_preservation_retention"
MASKED_SCHEMA = core.MASKED_SCHEMA
CONTEXT_LENGTH = core.CONTEXT_LENGTH
VOCAB_SIZE = core.VOCAB_SIZE


def _canonical(path: Path) -> str:
    return str(path).replace("\\", "/")


def _require_identity_policy(identity_index: Mapping[str, Any]) -> None:
    policy = identity_index.get("policy")
    if not isinstance(policy, Mapping):
        raise PermissionError("viv_slm_preservation_identity_policy_missing")
    if policy.get("identity_before_knowledge") is not True:
        raise PermissionError("viv_slm_preservation_identity_first_policy_invalid")
    if policy.get("knowledge_admission_for_identity_lanes") is not False:
        raise PermissionError("viv_slm_preservation_identity_lane_knowledge_admission_invalid")


def _base_training_layout(
    tensor_manifest: Mapping[str, Any],
    source_train_examples: int,
    lane: Mapping[str, Any],
) -> dict[str, int]:
    """Resolve the declarative base replay/dialogue expansion without guesswork."""

    splits = tensor_manifest.get("splits")
    train_split = splits.get("train") if isinstance(splits, Mapping) else None
    if not isinstance(train_split, Mapping):
        raise ValueError("viv_slm_preservation_base_train_split_metadata_missing")
    base_replay_examples = int(train_split.get("base_replay_examples", source_train_examples))
    dialogue_context_examples = int(train_split.get("dialogue_context_examples", 0))
    extra_repeats = int(lane.get("base_dialogue_extra_repeats", 0))
    if extra_repeats < 0:
        raise ValueError("viv_slm_preservation_dialogue_extra_repeats_invalid")
    if base_replay_examples <= 0 or dialogue_context_examples < 0:
        raise ValueError("viv_slm_preservation_base_train_split_metadata_invalid")
    if base_replay_examples + dialogue_context_examples != source_train_examples:
        raise ValueError("viv_slm_preservation_base_train_split_count_mismatch")
    return {
        "source_train_examples": source_train_examples,
        "base_replay_examples": base_replay_examples,
        "dialogue_context_examples": dialogue_context_examples,
        "dialogue_extra_repeats": extra_repeats,
        "effective_train_examples": base_replay_examples + dialogue_context_examples * (1 + extra_repeats),
    }


def load_lane_configuration(
    lane_id: str = DEFAULT_LANE_ID,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    Mapping[str, Any],
    Path,
    Path,
    Path,
    Path,
    float,
    int,
    int,
]:
    """Load and validate one central declarative preservation lane."""

    knob_path = TRAINING_ROOT / "current" / "TRAINING_KNOBS.json"
    knob_registry = core._read_json(knob_path)
    core._require_closed_knob_authority(knob_registry.get("authority", {}))

    identity = knob_registry.get("identity_data")
    if not isinstance(identity, Mapping):
        raise ValueError("viv_slm_preservation_identity_data_knobs_missing")
    lanes = identity.get("candidate_lanes")
    if not isinstance(lanes, Mapping):
        raise ValueError("viv_slm_preservation_candidate_lanes_missing")
    lane = lanes.get(lane_id)
    if not isinstance(lane, Mapping):
        raise KeyError(f"viv_slm_preservation_lane_not_declared:{lane_id}")

    index_path = viv_path(str(identity.get("index") or ""))
    identity_index = core._read_json(index_path)
    _require_identity_policy(identity_index)
    if lane.get("v16_validation_in_training") is not False:
        raise PermissionError("viv_slm_preservation_retention_validation_must_be_excluded")

    base_root = viv_path(str(lane.get("base_dataset") or ""))
    retention_root = viv_path(str(lane.get("retention_dataset") or ""))
    validation_root = viv_path(str(lane.get("validation_source") or ""))
    output_root = viv_path(str(lane.get("output_dataset") or ""))
    if _canonical(base_root) != _canonical(viv_path(str(identity.get("base_dataset") or ""))):
        raise ValueError("viv_slm_preservation_base_root_knob_mismatch")
    if _canonical(retention_root) != _canonical(viv_path(str(identity.get("retention_dataset") or ""))):
        raise ValueError("viv_slm_preservation_retention_root_knob_mismatch")
    if _canonical(validation_root) != _canonical(base_root):
        raise ValueError("viv_slm_preservation_validation_must_be_base_dataset")

    fraction = float(lane.get("retention_fraction_of_base_train"))
    seed = int(lane.get("retention_sampling_seed"))
    shard_size = int(identity.get("max_shard_examples"))
    if not 0.0 < fraction <= 1.0 or seed < 0 or shard_size <= 0:
        raise ValueError("viv_slm_preservation_lane_knob_bounds_invalid")

    base = core._manifest_contract(base_root, label="base_identity_dataset")
    retention = core._manifest_contract(retention_root, label="retention_identity_dataset")
    pinned_hashes = {
        "index_sha256": core._sha256(index_path),
        "base_input_manifest_sha256": base["input_manifest_sha256"],
        "base_tensor_manifest_sha256": base["tensor_manifest_sha256"],
        "retention_input_manifest_sha256": retention["input_manifest_sha256"],
        "retention_tensor_manifest_sha256": retention["tensor_manifest_sha256"],
    }
    for field, actual in pinned_hashes.items():
        expected = str(identity.get(field) or "")
        if expected and expected.casefold() != actual.casefold():
            raise ValueError(f"viv_slm_preservation_identity_data_hash_mismatch:{field}:{actual}")
    for field, actual in {
        "base_input_manifest_sha256": base["input_manifest_sha256"],
        "base_tensor_manifest_sha256": base["tensor_manifest_sha256"],
        "retention_input_manifest_sha256": retention["input_manifest_sha256"],
        "retention_tensor_manifest_sha256": retention["tensor_manifest_sha256"],
    }.items():
        expected = str(lane.get(field) or "")
        if expected and expected.casefold() != actual.casefold():
            raise ValueError(f"viv_slm_preservation_lane_hash_mismatch:{field}:{actual}")
    if base["vocab"].get("vocab") != retention["vocab"].get("vocab"):
        raise ValueError("viv_slm_preservation_vocab_content_mismatch")
    if base["input_manifest"].get("termination_marker") != retention["input_manifest"].get("termination_marker"):
        raise ValueError("viv_slm_preservation_termination_marker_mismatch")

    return (
        knob_registry,
        identity_index,
        identity,
        lane,
        base_root,
        retention_root,
        validation_root,
        output_root,
        fraction,
        seed,
        shard_size,
    )


def build_plan(lane_id: str = DEFAULT_LANE_ID) -> dict[str, Any]:
    (
        _knob_registry,
        identity_index,
        identity,
        lane,
        base_root,
        retention_root,
        validation_root,
        output_root,
        fraction,
        seed,
        shard_size,
    ) = load_lane_configuration(lane_id)
    base_manifest = core._read_json(base_root / "INPUT_MANIFEST.json")
    base_tensor_manifest = core._read_json(base_root / "tensor_dataset" / "MANIFEST.json")
    retention_manifest = core._read_json(retention_root / "INPUT_MANIFEST.json")
    base_count = int(base_manifest["train_examples"])
    base_layout = _base_training_layout(base_tensor_manifest, base_count, lane)
    retention_available = int(retention_manifest["train_examples"])
    retention_count = int(round(base_count * fraction))
    if retention_count <= 0 or retention_count > retention_available:
        raise ValueError("viv_slm_preservation_retention_count_invalid")
    return {
        "status": "DRY_RUN_READY",
        "lane_id": lane_id,
        "builder": _canonical(VIV_SLM_ROOT / Path(__file__).name),
        "knob_registry": {
            "path": _canonical(TRAINING_ROOT / "current" / "TRAINING_KNOBS.json"),
            "sha256": core._sha256(TRAINING_ROOT / "current" / "TRAINING_KNOBS.json"),
        },
        "identity_index": {
            "path": _canonical(viv_path(str(identity.get("index")))),
            "sha256": core._sha256(viv_path(str(identity.get("index")))),
            "identity_before_knowledge": identity_index["policy"]["identity_before_knowledge"],
            "knowledge_admission": identity_index["policy"]["knowledge_admission_for_identity_lanes"],
        },
        "base": {
            "root": _canonical(base_root),
            "train_examples": base_count,
            "source_train_examples": base_layout["source_train_examples"],
            "base_replay_examples": base_layout["base_replay_examples"],
            "dialogue_context_examples": base_layout["dialogue_context_examples"],
            "dialogue_extra_repeats": base_layout["dialogue_extra_repeats"],
            "effective_train_examples": base_layout["effective_train_examples"],
            "validation_examples": int(base_manifest["validation_examples"]),
            "input_manifest_sha256": core._sha256(base_root / "INPUT_MANIFEST.json"),
            "tensor_manifest_sha256": core._sha256(base_root / "tensor_dataset" / "MANIFEST.json"),
        },
        "retention": {
            "root": _canonical(retention_root),
            "source_train_examples": retention_available,
            "selected_train_examples": retention_count,
            "validation_examples_excluded": int(retention_manifest["validation_examples"]),
            "input_manifest_sha256": core._sha256(retention_root / "INPUT_MANIFEST.json"),
            "tensor_manifest_sha256": core._sha256(retention_root / "tensor_dataset" / "MANIFEST.json"),
        },
        "output": {
            "root": _canonical(output_root),
            "train_examples": base_layout["effective_train_examples"] + retention_count,
            "validation_source": _canonical(validation_root),
            "retention_fraction_of_base_train": fraction,
            "sampling_seed": seed,
            "max_shard_examples": shard_size,
        },
        "authority": {
            "training_authorized": False,
            "run_authorized": False,
            "promotion_authorized": False,
            "deployment_authorized": False,
            "knowledge_admission": False,
            "writes_live_model": False,
        },
    }


def _write_tensor_shard(
    path: Path,
    inputs: torch.Tensor,
    targets: torch.Tensor,
    masks: torch.Tensor,
) -> dict[str, Any]:
    payload = {
        "schema_version": MASKED_SCHEMA,
        "storage_dtype": "torch.int16",
        "loss_mask_dtype": "torch.bool",
        "inputs": inputs.to(dtype=torch.int16).contiguous(),
        "targets": targets.to(dtype=torch.int16).contiguous(),
        "loss_mask": masks.to(dtype=torch.bool).contiguous(),
    }
    torch.save(payload, path)
    return {
        "path": f"{path.parent.name}/{path.name}",
        "examples": int(inputs.shape[0]),
        "context_length": CONTEXT_LENGTH,
        "storage_dtype": "torch.int16",
        "loss_mask_dtype": "torch.bool",
        "masked_target_tokens": int(payload["loss_mask"].sum()),
        "sha256": core._sha256(path),
    }


def build(output_root: Path | None = None, lane_id: str = DEFAULT_LANE_ID) -> dict[str, Any]:
    (
        _knob_registry,
        identity_index,
        identity,
        lane,
        base_root,
        retention_root,
        validation_root,
        configured_output,
        fraction,
        seed,
        shard_size,
    ) = load_lane_configuration(lane_id)
    output_root = viv_path(output_root) if output_root is not None and not output_root.is_absolute() else output_root
    output_root = output_root or configured_output
    if output_root.exists():
        raise FileExistsError(f"viv_slm_preservation_output_exists_refuse_overwrite:{output_root}")

    base = core._manifest_contract(base_root, label="base_identity_dataset")
    retention = core._manifest_contract(retention_root, label="retention_identity_dataset")
    base_train_source, base_targets_source, base_masks_source, _ = core._load_split(
        base_root,
        "train",
        label="base_identity_dataset",
    )
    base_layout = _base_training_layout(
        base["tensor_manifest"],
        int(base_train_source.shape[0]),
        lane,
    )
    base_validation, _base_validation_targets, base_validation_masks, _ = core._load_split(
        validation_root,
        "validation",
        label="base_identity_validation",
    )
    retention_train, retention_targets, retention_masks, _ = core._load_split(
        retention_root,
        "train",
        label="retention_identity_dataset",
    )
    selected_count = int(round(base_train_source.shape[0] * fraction))
    if selected_count <= 0 or selected_count > retention_train.shape[0]:
        raise ValueError("viv_slm_preservation_retention_count_invalid")

    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    selected_indices = torch.randperm(retention_train.shape[0], generator=generator)[:selected_count]
    selected_indices = torch.sort(selected_indices).values
    if base_layout["dialogue_extra_repeats"] == 0:
        base_train = base_train_source
        base_targets = base_targets_source
        base_masks = base_masks_source
    else:
        dialogue_start = base_layout["base_replay_examples"]
        dialogue_inputs = base_train_source[dialogue_start:]
        dialogue_targets = base_targets_source[dialogue_start:]
        dialogue_masks = base_masks_source[dialogue_start:]
        repeat_count = 1 + base_layout["dialogue_extra_repeats"]
        base_train = torch.cat(
            (base_train_source[:dialogue_start], *([dialogue_inputs] * repeat_count)),
            dim=0,
        ).contiguous()
        base_targets = torch.cat(
            (base_targets_source[:dialogue_start], *([dialogue_targets] * repeat_count)),
            dim=0,
        ).contiguous()
        base_masks = torch.cat(
            (base_masks_source[:dialogue_start], *([dialogue_masks] * repeat_count)),
            dim=0,
        ).contiguous()
    if int(base_train.shape[0]) != base_layout["effective_train_examples"]:
        raise ValueError("viv_slm_preservation_effective_base_train_count_mismatch")
    train_inputs = torch.cat((base_train, retention_train[selected_indices]), dim=0).contiguous()
    train_targets = torch.cat((base_targets, retention_targets[selected_indices]), dim=0).contiguous()
    train_masks = torch.cat((base_masks, retention_masks[selected_indices]), dim=0).contiguous()

    build_root = output_root.parent / f".{output_root.name}.__building__"
    if build_root.exists():
        raise FileExistsError(f"viv_slm_preservation_build_staging_exists_refuse_overwrite:{build_root}")
    (build_root / "tensor_dataset" / "train").mkdir(parents=True)
    (build_root / "tensor_dataset" / "validation").mkdir(parents=True)
    shutil.copy2(base["vocab_path"], build_root / "VOCAB.json")

    train_records: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, train_inputs.shape[0], shard_size)):
        stop = min(start + shard_size, train_inputs.shape[0])
        train_records.append(
            _write_tensor_shard(
                build_root / "tensor_dataset" / "train" / f"shard_{index:05d}.pt",
                train_inputs[start:stop],
                train_targets[start:stop],
                train_masks[start:stop],
            )
        )

    validation_records: list[dict[str, Any]] = []
    for index, source in enumerate(sorted((validation_root / "tensor_dataset" / "validation").glob("shard_*.pt"))):
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
                "sha256": core._sha256(destination),
            }
        )

    base_source = {
        "root": _canonical(base_root),
        "input_manifest_sha256": base["input_manifest_sha256"],
        "tensor_manifest_sha256": base["tensor_manifest_sha256"],
        "train_examples_used": int(base_train.shape[0]),
    }
    if base_layout["dialogue_extra_repeats"]:
        base_source.update(
            {
                "source_train_examples": base_layout["source_train_examples"],
                "base_replay_examples": base_layout["base_replay_examples"],
                "dialogue_context_examples": base_layout["dialogue_context_examples"],
                "dialogue_extra_repeats": base_layout["dialogue_extra_repeats"],
            }
        )

    tensor_manifest = {
        "schema_version": "viv_slm_preservation_replay_tensor_dataset_v1",
        "lane_id": lane_id,
        "source_policy": "base_train_plus_deterministic_retention_train_only_response_only; base_validation_only",
        "objective": {
            "kind": "identity_preservation_replay",
            "context_length": CONTEXT_LENGTH,
            "loss_mask": "Viv_response_and_end_marker_only",
            "validation_source": "base_identity_dataset",
            "retention_validation_in_training": False,
        },
        "sources": {
            "base": base_source,
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
                "source": "base_identity_dataset",
                "masked_target_tokens": int(base_validation_masks.sum()),
                "shards": validation_records,
            },
        },
    }
    core._write_json(build_root / "tensor_dataset" / "MANIFEST.json", tensor_manifest)

    input_manifest = {
        "schema_version": "viv_slm_preservation_replay_inputs_v1",
        "status": "COMPLETE_TRAINING_CLOSED",
        "lane_id": lane_id,
        "model": "Viv-SLM",
        "context_length": CONTEXT_LENGTH,
        "vocab_size": VOCAB_SIZE,
        "vocab_manifest": _canonical(output_root / "VOCAB.json"),
        "vocab_manifest_sha256": core._sha256(build_root / "VOCAB.json"),
        "tensor_manifest": _canonical(output_root / "tensor_dataset" / "MANIFEST.json"),
        "tensor_manifest_sha256": core._sha256(build_root / "tensor_dataset" / "MANIFEST.json"),
        "termination_marker": base["input_manifest"].get("termination_marker"),
        "response_only_loss": True,
        "world_knowledge_included": False,
        "base_dataset": {
            "root": _canonical(base_root),
            "input_manifest_sha256": base["input_manifest_sha256"],
            "tensor_manifest_sha256": base["tensor_manifest_sha256"],
        },
        "retention_dataset": {
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
        "validation_source": "base_identity_dataset_only",
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
    if base_layout["dialogue_extra_repeats"]:
        input_manifest.update(
            {
                "base_source_train_examples": base_layout["source_train_examples"],
                "base_replay_examples": base_layout["base_replay_examples"],
                "dialogue_context_examples": base_layout["dialogue_context_examples"],
                "dialogue_extra_repeats": base_layout["dialogue_extra_repeats"],
                "effective_base_train_examples": base_layout["effective_train_examples"],
            }
        )
    core._write_json(build_root / "INPUT_MANIFEST.json", input_manifest)
    build_root.rename(output_root)
    return {
        "status": "BUILT_HASH_VERIFIED",
        "lane_id": lane_id,
        "output_root": _canonical(output_root),
        "input_manifest_sha256": core._sha256(output_root / "INPUT_MANIFEST.json"),
        "tensor_manifest_sha256": core._sha256(output_root / "tensor_dataset" / "MANIFEST.json"),
        "vocab_sha256": core._sha256(output_root / "VOCAB.json"),
        "train_examples": int(train_inputs.shape[0]),
        "validation_examples": int(base_validation.shape[0]),
        "base_examples": int(base_train.shape[0]),
        "base_source_examples": base_layout["source_train_examples"],
        "base_replay_examples": base_layout["base_replay_examples"],
        "dialogue_context_examples": base_layout["dialogue_context_examples"],
        "dialogue_extra_repeats": base_layout["dialogue_extra_repeats"],
        "retention_examples": selected_count,
        "retention_fraction_of_base_train": fraction,
        "sampling_seed": seed,
        "validation_source": "base_identity_dataset_only",
        "retention_validation_in_training": False,
        "authority": {
            "training_authorized": False,
            "run_authorized": False,
            "knowledge_admission": False,
            "live_model_changed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", default=DEFAULT_LANE_ID)
    parser.add_argument("--dry-run", action="store_true", help="Validate one declarative lane without writing tensors.")
    parser.add_argument("--build", action="store_true", help="Build one new canonical identity input package.")
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args()
    if args.dry_run == args.build:
        parser.error("choose exactly one of --dry-run or --build")
    result = build_plan(args.lane) if args.dry_run else build(args.output_root, args.lane)
    print(core.json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
