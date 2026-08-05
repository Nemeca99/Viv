#!/usr/bin/env python3
"""Regression checks for the V26 narrow surface-discrimination input lane."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
DEFAULT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v26_surface_discrimination" / "inputs"
EXPECTED_INTENTS = ["greeting", "plain_language", "presence", "speech_style"]
EXPECTED_CONCEPTS = ["gpu_renderer"]


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(root: Path = DEFAULT_ROOT) -> dict[str, object]:
    input_manifest = _read(root / "INPUT_MANIFEST.json")
    tensor_manifest = _read(root / "tensor_dataset" / "MANIFEST.json")
    train = tensor_manifest["splits"]["train"]
    validation = tensor_manifest["splits"]["validation"]
    shards = list(train["shards"]) + list(validation["shards"])
    paths = [str(row["path"]) for row in shards]
    if input_manifest["schema_version"] != "viv_slm_v26_surface_discrimination_inputs_v1":
        raise AssertionError("v26_input_schema_mismatch")
    if input_manifest["focus_repeats"] != 24:
        raise AssertionError("v26_focus_repeat_mismatch")
    if input_manifest["focus_intents"] != EXPECTED_INTENTS:
        raise AssertionError("v26_focus_intents_mismatch")
    if input_manifest["focus_concepts"] != EXPECTED_CONCEPTS:
        raise AssertionError("v26_focus_concepts_mismatch")
    if train["focused_rows"] != 57:
        raise AssertionError(f"v26_focused_row_count_mismatch:{train['focused_rows']}")
    if train["base_examples"] != 53314:
        raise AssertionError(f"v26_base_example_count_mismatch:{train['base_examples']}")
    if validation["examples"] != 8672:
        raise AssertionError(f"v26_validation_example_count_mismatch:{validation['examples']}")
    if len(paths) != len(set(paths)):
        raise AssertionError("v26_shard_path_collision")
    if input_manifest["validation_unchanged_from_v24"] is not True:
        raise AssertionError("v26_validation_mutation_declared")
    if input_manifest["response_only_loss"] is not True:
        raise AssertionError("v26_response_only_loss_missing")
    if input_manifest["world_knowledge_included"] is not False:
        raise AssertionError("v26_world_knowledge_policy_violation")
    if input_manifest["training_authorized"] is not False or input_manifest["run_authorized"] is not False:
        raise AssertionError("v26_inputs_must_start_authority_closed")
    return {
        "status": "VIV_SLM_V26_SURFACE_DISCRIMINATION_INPUTS_PASS",
        "train_examples": input_manifest["train_examples"],
        "base_train_examples": input_manifest["base_train_examples"],
        "focused_train_examples": input_manifest["focused_train_examples"],
        "focused_rows": train["focused_rows"],
        "validation_examples": input_manifest["validation_examples"],
        "focus_repeats": input_manifest["focus_repeats"],
        "validation_unchanged": input_manifest["validation_unchanged_from_v24"],
        "response_only_loss": input_manifest["response_only_loss"],
        "world_knowledge": input_manifest["world_knowledge_included"],
        "training_authorized": input_manifest["training_authorized"],
        "shard_paths_unique": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    print(json.dumps(run(args.root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
