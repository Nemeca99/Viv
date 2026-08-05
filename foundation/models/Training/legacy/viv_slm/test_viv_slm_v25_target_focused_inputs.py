#!/usr/bin/env python3
"""Regression tests for the V25 dual-view target-focused inputs."""
from __future__ import annotations

import json
from pathlib import Path

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
INPUTS = VIV_ROOT / "models" / "viv_slm_identity_personality_v25_target_focused" / "inputs"


def main() -> int:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    tensor_manifest = json.loads((INPUTS / "tensor_dataset" / "MANIFEST.json").read_text(encoding="utf-8"))
    train = tensor_manifest["splits"]["train"]
    validation = tensor_manifest["splits"]["validation"]
    assert manifest["schema_version"] == "viv_slm_v25_target_focused_inputs_v1"
    assert manifest["payload_schema_version"] == "viv_slm_response_only_tensor_dataset_v1"
    assert manifest["target_focused"] is True
    assert manifest["focus_view"] == "position_aligned_train_only"
    assert manifest["focus_repeats"] == 8
    assert manifest["validation_unchanged_from_v24"] is True
    assert manifest["world_knowledge_included"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert tensor_manifest["objective"]["focus_prompt_position"] == 0
    assert tensor_manifest["objective"]["focus_target_coverage"] == "complete"
    assert train["focused_rows"] > 0
    assert train["focused_examples"] > 0
    assert train["examples"] == train["base_examples"] + train["focused_examples"]
    assert validation["focused_examples"] == 0
    assert validation["examples"] == manifest["validation_examples"]

    checked = 0
    focus_shards = 0
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
    assert checked == manifest["train_examples"] + manifest["validation_examples"]
    assert any(shard["view"] == "v25_position_aligned_focus" for shard in train["shards"])
    assert all(shard["view"] == "v24_packed_base" for shard in validation["shards"])
    print(
        "VIV_SLM_V25_TARGET_FOCUSED_INPUTS_PASS "
        f"train_examples={manifest['train_examples']} base_train_examples={manifest['base_train_examples']} "
        f"focused_train_examples={manifest['focused_train_examples']} focused_rows={manifest['focused_train_rows']} "
        f"validation_examples={manifest['validation_examples']} checked_examples={checked} "
        "focus_prompt_position=0 focus_repeats=8 validation_unchanged=true "
        "response_only_loss=true world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
