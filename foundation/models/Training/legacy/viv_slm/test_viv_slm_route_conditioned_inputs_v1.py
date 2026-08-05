#!/usr/bin/env python3
"""Verify CPU-owned route conditioning and complete response targets."""
from __future__ import annotations

import json
from pathlib import Path

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v22_route_conditioned" / "inputs"


def _shards(split: str) -> list[Path]:
    return sorted((INPUTS / "tensor_dataset" / split).glob("shard_*.pt"))


def main() -> int:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    tensor_manifest = json.loads((INPUTS / "tensor_dataset" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_training_inputs_route_conditioned_v1"
    assert manifest["route_conditioned"] is True
    assert manifest["route_owner"] == "cpu"
    assert manifest["route_header"] == "Route"
    assert manifest["dialogue_aligned"] is True
    assert manifest["chunked"] is True
    assert manifest["response_only_loss"] is True
    assert manifest["train_rows"] == 366
    assert manifest["validation_rows"] == 64
    assert manifest["train_examples"] == 636
    assert manifest["validation_examples"] == 122
    assert manifest["truncated_rows"] == 0
    assert manifest["target_coverage"] == "complete"
    assert manifest["route_counts"] == {
        "train": {"architecture": 74, "conversation": 158, "evidence": 51, "identity": 66, "system": 17},
        "validation": {"architecture": 18, "conversation": 18, "evidence": 8, "identity": 16, "system": 4},
    }
    assert manifest["world_knowledge_included"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert tensor_manifest["schema_version"] == "viv_slm_route_conditioned_chunked_tensor_dataset_v1"
    assert tensor_manifest["route_conditioning"]["owner"] == "cpu"
    assert tensor_manifest["objective"]["target_coverage"] == "every_response_and_end_marker_character_exactly_once"
    for split, expected_examples in (("train", 636), ("validation", 122)):
        shards = _shards(split)
        assert shards
        loaded = 0
        shard_manifests = tensor_manifest["splits"][split]["shards"]
        assert len(shard_manifests) == len(shards)
        for shard, shard_manifest in zip(shards, shard_manifests):
            payload = torch.load(shard, map_location="cpu", weights_only=True)
            assert payload["schema_version"] == "viv_slm_route_conditioned_chunked_tensor_dataset_v1"
            assert payload["inputs"].shape[1] == 128
            assert payload["targets"].shape == payload["inputs"].shape
            assert payload["loss_mask"].dtype == torch.bool
            assert payload["loss_mask"].shape == payload["inputs"].shape
            assert bool(payload["loss_mask"].any())
            assert all(route in {"architecture", "conversation", "evidence", "identity", "system"} for route in shard_manifest["routes"])
            loaded += int(payload["inputs"].shape[0])
        assert loaded == expected_examples
    print({"ok": True, "dataset": "v22_route_conditioned", "train_examples": 636, "validation_examples": 122, "route_owner": "cpu", "truncated_rows": 0, "target_coverage": "complete", "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
