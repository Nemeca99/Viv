#!/usr/bin/env python3
"""Regression checks for V28's canonical two-surface input extension."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
DEFAULT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v28_canonical_disambiguation" / "inputs"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(root: Path = DEFAULT_ROOT) -> dict[str, object]:
    input_manifest = _read(root / "INPUT_MANIFEST.json")
    tensor_manifest = _read(root / "tensor_dataset" / "MANIFEST.json")
    train = tensor_manifest["splits"]["train"]
    validation = tensor_manifest["splits"]["validation"]
    paths = [str(row["path"]) for row in list(train["shards"]) + list(validation["shards"])]
    if input_manifest["schema_version"] != "viv_slm_v28_canonical_disambiguation_inputs_v1":
        raise AssertionError("v28_input_schema_mismatch")
    if input_manifest["base_replay"] != "v27_replay_anchored_unchanged":
        raise AssertionError("v28_base_replay_mismatch")
    if input_manifest["canonical_disambiguation_repeats"] != 16:
        raise AssertionError("v28_repeat_mismatch")
    if input_manifest["canonical_disambiguation_rows"] != 23:
        raise AssertionError(f"v28_canonical_row_count_mismatch:{input_manifest['canonical_disambiguation_rows']}")
    if input_manifest["base_train_examples"] != 46673:
        raise AssertionError(f"v28_base_example_count_mismatch:{input_manifest['base_train_examples']}")
    if input_manifest["prior_focused_train_examples"] != 472:
        raise AssertionError(f"v28_prior_focus_count_mismatch:{input_manifest['prior_focused_train_examples']}")
    if input_manifest["additional_canonical_examples"] <= 0:
        raise AssertionError("v28_canonical_examples_missing")
    if validation["examples"] != 8672 or input_manifest["validation_unchanged_from_v17"] is not True:
        raise AssertionError("v28_validation_contract_violation")
    if len(paths) != len(set(paths)):
        raise AssertionError("v28_shard_path_collision")
    if input_manifest["response_only_loss"] is not True or input_manifest["world_knowledge_included"] is not False:
        raise AssertionError("v28_policy_violation")
    if input_manifest["training_authorized"] is not False or input_manifest["run_authorized"] is not False:
        raise AssertionError("v28_inputs_must_start_authority_closed")
    if not any(row["view"] == "v28_canonical_disambiguation_focus" for row in train["shards"]):
        raise AssertionError("v28_focus_shard_missing")
    return {
        "status": "VIV_SLM_V28_CANONICAL_DISAMBIGUATION_INPUTS_PASS",
        "train_examples": input_manifest["train_examples"],
        "base_train_examples": input_manifest["base_train_examples"],
        "prior_focused_train_examples": input_manifest["prior_focused_train_examples"],
        "additional_canonical_examples": input_manifest["additional_canonical_examples"],
        "canonical_rows": input_manifest["canonical_disambiguation_rows"],
        "validation_examples": input_manifest["validation_examples"],
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
