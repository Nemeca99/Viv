#!/usr/bin/env python3
"""Verify V21 chunked dialogue alignment preserves all response targets."""
from __future__ import annotations

import json
from pathlib import Path

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v21_dialogue_aligned_v2" / "inputs"


def _shards(split: str) -> list[Path]:
    return sorted((INPUTS / "tensor_dataset" / split).glob("shard_*.pt"))


def main() -> int:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    tensor_manifest = json.loads((INPUTS / "tensor_dataset" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_training_inputs_dialogue_aligned_chunked_v2"
    assert manifest["dialogue_aligned"] is True
    assert manifest["chunked"] is True
    assert manifest["response_only_loss"] is True
    assert manifest["context_length"] == 128
    assert manifest["train_rows"] == 366
    assert manifest["validation_rows"] == 64
    assert manifest["train_examples"] == 520
    assert manifest["validation_examples"] == 101
    assert manifest["truncated_rows"] == 0
    assert manifest["target_coverage"] == "complete"
    assert manifest["world_knowledge_included"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert tensor_manifest["schema_version"] == "viv_slm_dialogue_aligned_chunked_tensor_dataset_v2"
    assert tensor_manifest["objective"]["first_chunk_prompt_position"] == 0
    assert tensor_manifest["objective"]["target_coverage"] == "every_response_and_end_marker_character_exactly_once"
    assert tensor_manifest["splits"]["train"]["truncated_rows"] == []
    assert tensor_manifest["splits"]["validation"]["truncated_rows"] == []
    for split, expected_examples in (("train", 520), ("validation", 101)):
        shards = _shards(split)
        assert shards
        loaded = 0
        for shard in shards:
            payload = torch.load(shard, map_location="cpu", weights_only=True)
            assert payload["schema_version"] == "viv_slm_dialogue_aligned_chunked_tensor_dataset_v2"
            assert payload["inputs"].shape[1] == 128
            assert payload["targets"].shape == payload["inputs"].shape
            assert payload["loss_mask"].dtype == torch.bool
            assert payload["loss_mask"].shape == payload["inputs"].shape
            assert bool(payload["loss_mask"].any())
            loaded += int(payload["inputs"].shape[0])
        assert loaded == expected_examples
    print({"ok": True, "dataset": "v21_dialogue_aligned_chunked", "train_examples": 520, "validation_examples": 101, "truncated_rows": 0, "target_coverage": "complete", "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
