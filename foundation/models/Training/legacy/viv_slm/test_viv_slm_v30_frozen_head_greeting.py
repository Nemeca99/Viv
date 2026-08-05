#!/usr/bin/env python3
"""Preflight the V30 frozen-head greeting correction contract."""
from __future__ import annotations

import json
from pathlib import Path

from train_viv_slm_v30_frozen_head_greeting import (
    EXPECTED_PARENT_CHECKPOINT_SHA256,
    FOCUS_VIEW,
    TRAINABLE_PARAMETER_NAMES,
    validate_sources,
)


def main() -> int:
    source = validate_sources()
    base_manifest = source["base_manifest"]
    focus_manifest = source["focus_manifest"]
    if source["parent_checkpoint_sha256"] != EXPECTED_PARENT_CHECKPOINT_SHA256:
        raise AssertionError("v30_parent_hash_changed")
    if base_manifest.get("validation_unchanged_from_v17") is not True:
        raise AssertionError("v30_validation_replay_not_frozen")
    if focus_manifest.get("training_authorized") is not False:
        raise AssertionError("v30_focus_input_training_authority_open")
    if source["focus_shard_manifest"].get("view") != FOCUS_VIEW:
        raise AssertionError("v30_focus_view_mismatch")
    if tuple(TRAINABLE_PARAMETER_NAMES) != ("lm_head.weight", "lm_head.bias"):
        raise AssertionError("v30_trainable_scope_constant_changed")
    if source["focus_inputs"].shape != source["focus_targets"].shape:
        raise AssertionError("v30_focus_input_target_shape_mismatch")
    if source["focus_masks"].shape != source["focus_inputs"].shape:
        raise AssertionError("v30_focus_mask_shape_mismatch")
    if not bool(source["focus_masks"].any()):
        raise AssertionError("v30_focus_mask_empty")
    print(json.dumps({
        "status": "VIV_SLM_V30_FROZEN_HEAD_PREFLIGHT_PASS",
        "parent_checkpoint_sha256": source["parent_checkpoint_sha256"],
        "focus_view": FOCUS_VIEW,
        "focus_examples": int(source["focus_inputs"].shape[0]),
        "trainable_parameter_names": list(TRAINABLE_PARAMETER_NAMES),
        "validation_unchanged_from_v17": True,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
