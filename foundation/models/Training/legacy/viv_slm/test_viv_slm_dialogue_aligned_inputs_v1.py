#!/usr/bin/env python3
"""Verify position-aligned response-only dialogue inputs."""
from __future__ import annotations

import json
from pathlib import Path
import torch

FOUNDATION = Path(__file__).resolve().parents[1]
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v3_dialogue_aligned" / "inputs"


def main() -> int:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    tensor_manifest = json.loads((INPUTS / "tensor_dataset" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_training_inputs_dialogue_aligned_v1"
    assert manifest["dialogue_aligned"] is True
    assert manifest["response_only_loss"] is True
    assert manifest["termination_marker"] == "<END>"
    assert manifest["world_knowledge_included"] is False
    assert manifest["training_authorized"] is False
    assert tensor_manifest["schema_version"] == "viv_slm_dialogue_aligned_tensor_dataset_v1"
    assert tensor_manifest["objective"]["prompt_position"] == 0
    for split in ("train", "validation"):
        shard = INPUTS / "tensor_dataset" / split / "shard_00000.pt"
        payload = torch.load(shard, map_location="cpu", weights_only=True)
        assert payload["schema_version"] == "viv_slm_dialogue_aligned_tensor_dataset_v1"
        assert payload["inputs"].shape[1] == 128
        assert payload["loss_mask"].dtype == torch.bool
        assert payload["loss_mask"].shape == payload["inputs"].shape
        assert bool(payload["loss_mask"].any())
    print(
        "VIV_SLM_DIALOGUE_ALIGNED_INPUTS_PASS "
        f"train_examples={manifest['train_examples']} validation_examples={manifest['validation_examples']} "
        "context=128 prompt_position=0 response_only_loss=true termination=<END> "
        "world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
