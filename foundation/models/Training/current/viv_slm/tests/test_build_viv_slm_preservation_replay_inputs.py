#!/usr/bin/env python3
"""Focused dry-run test for declarative identity preservation lanes."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_viv_slm_preservation_replay_inputs as builder  # noqa: E402


LANE_ID = "v61_stratified_preservation_retention"
V62_LANE_ID = "v62_dialogue_visibility_preservation"


def main() -> int:
    plan = builder.build_plan(LANE_ID)
    assert plan["status"] == "DRY_RUN_READY"
    assert plan["lane_id"] == LANE_ID
    assert plan["authority"]["training_authorized"] is False
    assert plan["authority"]["run_authorized"] is False
    assert plan["authority"]["knowledge_admission"] is False
    assert plan["identity_index"]["identity_before_knowledge"] is True
    assert plan["identity_index"]["knowledge_admission"] is False
    assert plan["base"]["train_examples"] == 55106
    assert plan["base"]["validation_examples"] == 8696
    assert plan["retention"]["selected_train_examples"] == 11021
    assert plan["retention"]["validation_examples_excluded"] == 8672
    assert plan["output"]["train_examples"] == 66127
    assert plan["output"]["validation_source"].endswith("v43_conversation_focus")
    v62_plan = builder.build_plan(V62_LANE_ID)
    assert v62_plan["status"] == "DRY_RUN_READY"
    assert v62_plan["base"]["dialogue_extra_repeats"] == 1
    assert v62_plan["base"]["effective_train_examples"] == 56898
    assert v62_plan["output"]["train_examples"] == 67919
    assert v62_plan["retention"]["selected_train_examples"] == 11021
    assert v62_plan["authority"]["training_authorized"] is False
    assert v62_plan["authority"]["knowledge_admission"] is False
    v62_root = Path(v62_plan["output"]["root"])
    assert v62_root.joinpath("INPUT_MANIFEST.json").is_file()
    input_manifest = builder.core._read_json(v62_root / "INPUT_MANIFEST.json")
    tensor_manifest = builder.core._read_json(v62_root / "tensor_dataset" / "MANIFEST.json")
    assert input_manifest["train_examples"] == 67919
    assert input_manifest["dialogue_extra_repeats"] == 1
    assert tensor_manifest["splits"]["train"]["examples"] == 67919
    assert tensor_manifest["sources"]["base"]["dialogue_extra_repeats"] == 1
    print("viv_slm_preservation_replay_builder_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
