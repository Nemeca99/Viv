#!/usr/bin/env python3
"""Verify v3 model inputs for the targeted identity repair lane."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v3" / "inputs"


def main() -> int:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    vocab = json.loads((INPUTS / "VOCAB.json").read_text(encoding="utf-8"))
    tensors = json.loads((INPUTS / "tensor_dataset" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["vocab_size"] == 96
    assert manifest["termination_marker"] == "<END>"
    assert manifest["world_knowledge_included"] is False
    assert manifest["training_authorized"] is False
    assert vocab["vocab_size"] == 96
    assert tensors["objective"]["context_length"] == 128
    assert tensors["objective"]["stride"] == 1
    assert tensors["splits"]["train"]["examples"] == manifest["train_examples"]
    assert tensors["splits"]["validation"]["examples"] == manifest["validation_examples"]
    print(
        "VIV_SLM_TRAINING_INPUTS_V3_PASS "
        f"vocab_size={manifest['vocab_size']} train_examples={manifest['train_examples']} "
        f"validation_examples={manifest['validation_examples']} context=128 stride=1 "
        "termination=<END> world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
