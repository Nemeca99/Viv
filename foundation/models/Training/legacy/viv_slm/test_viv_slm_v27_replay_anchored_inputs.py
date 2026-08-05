#!/usr/bin/env python3
"""Regression checks for V27's V17 replay-anchored input lane."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
DEFAULT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v27_replay_anchored" / "inputs"
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
    if input_manifest["schema_version"] != "viv_slm_v27_replay_anchored_inputs_v1":
        raise AssertionError("v27_input_schema_mismatch")
    if input_manifest["base_replay"] != "v17_original_packed_response_only":
        raise AssertionError("v27_base_replay_mismatch")
    if input_manifest["focus_repeats"] != 8:
        raise AssertionError("v27_focus_repeat_mismatch")
    if input_manifest["focus_intents"] != EXPECTED_INTENTS or input_manifest["focus_concepts"] != EXPECTED_CONCEPTS:
        raise AssertionError("v27_focus_definition_mismatch")
    if train["base_examples"] != 46673:
        raise AssertionError(f"v27_base_example_count_mismatch:{train['base_examples']}")
    if train["focused_rows"] != 57:
        raise AssertionError(f"v27_focused_row_count_mismatch:{train['focused_rows']}")
    if validation["examples"] != 8672:
        raise AssertionError(f"v27_validation_example_count_mismatch:{validation['examples']}")
    if len(paths) != len(set(paths)):
        raise AssertionError("v27_shard_path_collision")
    if input_manifest["validation_unchanged_from_v17"] is not True:
        raise AssertionError("v27_validation_mutation_declared")
    if input_manifest["response_only_loss"] is not True or input_manifest["world_knowledge_included"] is not False:
        raise AssertionError("v27_training_objective_policy_violation")
    if input_manifest["training_authorized"] is not False or input_manifest["run_authorized"] is not False:
        raise AssertionError("v27_inputs_must_start_authority_closed")
    if not any(row["view"] == "v17_replay_base" for row in train["shards"]):
        raise AssertionError("v27_base_view_missing")
    if not any(row["view"] == "v27_small_surface_focus" for row in train["shards"]):
        raise AssertionError("v27_focus_view_missing")
    return {
        "status": "VIV_SLM_V27_REPLAY_ANCHORED_INPUTS_PASS",
        "train_examples": input_manifest["train_examples"],
        "base_train_examples": input_manifest["base_train_examples"],
        "focused_train_examples": input_manifest["focused_train_examples"],
        "focused_rows": train["focused_rows"],
        "validation_examples": input_manifest["validation_examples"],
        "focus_repeats": input_manifest["focus_repeats"],
        "validation_unchanged": input_manifest["validation_unchanged_from_v17"],
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
