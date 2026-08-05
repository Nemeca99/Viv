#!/usr/bin/env python3
"""Verify the v5 character-model input tensors and manifest."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v5" / "inputs"


def main() -> int:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["schema_version"] == "viv_slm_training_inputs_v1"
    assert manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v5/MANIFEST.json")
    assert manifest["vocab_size"] == 96
    assert manifest["context_length"] == 128
    assert manifest["stride"] == 1
    assert manifest["train_examples"] == 20625
    assert manifest["validation_examples"] == 4482
    assert manifest["termination_marker"] == "<END>"
    assert manifest["world_knowledge_included"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["promotion_authorized"] is False
    assert manifest["deployment_changed"] is False
    assert manifest["live_model_changed"] is False
    print(
        "VIV_SLM_TRAINING_INPUTS_V5_PASS "
        f"vocab_size={manifest['vocab_size']} train_examples={manifest['train_examples']} "
        f"validation_examples={manifest['validation_examples']} context=128 stride=1 "
        "termination=<END> world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
