#!/usr/bin/env python3
"""Verify response-only tensors built from the V24 canonical corpus."""
from __future__ import annotations

import json
from pathlib import Path

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
INPUTS = VIV_ROOT / "models" / "viv_slm_identity_personality_v24_canonical_surface" / "inputs"
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v24"


def main() -> int:
    input_manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    tensor_manifest = json.loads((INPUTS / "tensor_dataset" / "MANIFEST.json").read_text(encoding="utf-8"))
    dataset_manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    assert input_manifest["schema_version"] == "viv_slm_training_inputs_response_only_v1"
    assert input_manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v24/MANIFEST.json")
    assert input_manifest["response_only_loss"] is True
    assert input_manifest["termination_marker"] == "<END>"
    assert input_manifest["world_knowledge_included"] is False
    assert input_manifest["training_authorized"] is False
    assert input_manifest["run_authorized"] is False
    assert tensor_manifest["schema_version"] == "viv_slm_response_only_tensor_dataset_v1"
    assert tensor_manifest["objective"]["loss_mask"] == "assistant_response_and_end_marker_only"
    assert dataset_manifest["row_counts"] == {"adversarial": 32, "frozen": 32, "train": 430, "validation": 64}
    assert input_manifest["vocab_size"] == 96

    checked = 0
    masked = 0
    for split in ("train", "validation"):
        split_dir = INPUTS / "tensor_dataset" / split
        shards = sorted(split_dir.glob("shard_*.pt"))
        assert shards
        for shard in shards:
            payload = torch.load(shard, map_location="cpu", weights_only=True)
            assert payload["schema_version"] == "viv_slm_response_only_tensor_dataset_v1"
            assert payload["loss_mask"].dtype == torch.bool
            assert payload["loss_mask"].shape == payload["inputs"].shape == payload["targets"].shape
            assert payload["inputs"].ndim == 2 and payload["inputs"].shape[1] == 128
            assert int(payload["inputs"].min()) >= 0 and int(payload["inputs"].max()) < 96
            assert int(payload["targets"].min()) >= 0 and int(payload["targets"].max()) < 96
            assert bool(payload["loss_mask"].any())
            checked += int(payload["inputs"].shape[0])
            masked += int(payload["loss_mask"].sum())
    assert checked == input_manifest["train_examples"] + input_manifest["validation_examples"]
    assert masked > 0
    print(
        "VIV_SLM_V24_RESPONSE_ONLY_INPUTS_PASS "
        f"train_examples={input_manifest['train_examples']} "
        f"validation_examples={input_manifest['validation_examples']} "
        f"checked_examples={checked} masked_tokens={masked} context=128 stride=1 "
        "response_only_loss=true parent_holdouts_preserved=true "
        "world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
