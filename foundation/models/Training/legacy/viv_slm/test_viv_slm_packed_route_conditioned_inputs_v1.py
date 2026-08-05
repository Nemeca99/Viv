#!/usr/bin/env python3
"""Regression checks for the V23 packed CPU-route-conditioned input lane."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
DEFAULT_INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v23_packed_route_conditioned" / "inputs"
EXPECTED_ROUTES = {"architecture", "conversation", "evidence", "identity", "system"}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test(input_root: Path) -> dict:
    input_manifest = _read(input_root / "INPUT_MANIFEST.json")
    tensor_manifest = _read(input_root / "tensor_dataset" / "MANIFEST.json")
    vocab_manifest = _read(input_root / "VOCAB.json")
    if input_manifest.get("schema_version") != "viv_slm_training_inputs_packed_route_conditioned_response_only_v1":
        raise AssertionError("v23_input_schema")
    if tensor_manifest.get("schema_version") != "viv_slm_packed_route_conditioned_response_only_tensor_dataset_v1":
        raise AssertionError("v23_tensor_schema")
    if input_manifest.get("route_conditioned") is not True or input_manifest.get("route_owner") != "cpu":
        raise AssertionError("v23_cpu_route_contract")
    if tensor_manifest.get("route_conditioning", {}).get("enabled") is not True:
        raise AssertionError("v23_route_conditioning_manifest")
    if set(input_manifest.get("route_mapping", {})) != EXPECTED_ROUTES:
        raise AssertionError("v23_route_mapping")
    if input_manifest.get("train_rows") != 366 or input_manifest.get("validation_rows") != 64:
        raise AssertionError("v23_source_row_counts")
    if input_manifest.get("train_examples", 0) <= 40000 or input_manifest.get("validation_examples", 0) <= 7000:
        raise AssertionError("v23_packed_training_scale_regressed")
    if vocab_manifest.get("vocab_size") != 96:
        raise AssertionError("v23_vocab_size")
    for split_name in ("train", "validation"):
        split = tensor_manifest["splits"][split_name]
        if set(split.get("route_counts", {})) != EXPECTED_ROUTES or sum(split["route_counts"].values()) != split["rows"]:
            raise AssertionError(f"v23_{split_name}_route_counts")
        if split["examples"] != input_manifest[f"{split_name}_examples"]:
            raise AssertionError(f"v23_{split_name}_example_count")
        shard_path = input_root / "tensor_dataset" / split_name / Path(split["shards"][0]["path"]).name
        payload = torch.load(shard_path, map_location="cpu", weights_only=True)
        inputs, targets, mask = payload["inputs"], payload["targets"], payload["loss_mask"]
        if tuple(inputs.shape[1:]) != (128,) or inputs.shape != targets.shape or inputs.shape != mask.shape:
            raise AssertionError(f"v23_{split_name}_tensor_shapes")
        if mask.dtype != torch.bool or not bool(mask.any()) or bool(mask[0, 0]):
            raise AssertionError(f"v23_{split_name}_response_mask")
        if not torch.equal(targets[:, :-1], inputs[:, 1:]):
            raise AssertionError(f"v23_{split_name}_causal_shift")
    for split_name in ("train", "validation"):
        source_path = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v17" / f"{split_name}.jsonl"
        rows = [json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if any("master s_n" in str(row.get("response", "")).casefold() or "rid=" in str(row.get("response", "")).casefold() for row in rows):
            raise AssertionError(f"v23_{split_name}_telemetry_response")
    return {"ok": True, "dataset": "v23_packed_route_conditioned", "train_examples": input_manifest["train_examples"], "validation_examples": input_manifest["validation_examples"], "route_owner": input_manifest["route_owner"], "response_only_loss": input_manifest["response_only_loss"], "packed_scale_preserved": True, "training_authorized": input_manifest["training_authorized"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    args = parser.parse_args(argv)
    print(json.dumps(test(args.input_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
