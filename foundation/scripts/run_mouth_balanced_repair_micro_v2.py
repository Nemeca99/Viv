#!/usr/bin/env python3
"""Second governed balanced repair micro at a conservative update dose."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION / "scripts"))
sys.path.insert(0, str(FOUNDATION))

import run_mouth_identity_refinement_v1 as base  # noqa: E402

ROOT = FOUNDATION / (
    "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/"
    "campaigns/mouth_balanced_repair_micro_v2"
)
TRAIN = FOUNDATION / (
    "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/"
    "campaigns/mouth_balanced_repair_micro_v1/train_8.jsonl"
)
PARENT = FOUNDATION / "models/Training/runs/mouth_cross_axis_micro_v1/adapter_step_8"
ID = "mouth_balanced_repair_micro_v2"

base.ROOT = ROOT
base.TRAIN = TRAIN
base.PARENT = PARENT
base.ID = ID
base.OPTIMIZER_ROWS = 8
base.OPTIMIZER_STEPS = 8
base.LEARNING_RATE = 1e-6
base.CHECKPOINT_STEPS = (2, 4, 6, 8)
base.ANCHOR_STRENGTH = 0.0
base.PROMPT = (
    "You are Viv's GPU mouth inside AIOS. CPU reasoning and supplied facts "
    "are authoritative. For identity questions explicitly say I am Viv, the "
    "AIOS identity, before describing the replaceable model voice. Do not "
    "claim human identity or independent tool agency."
)


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("install-preflight", "preflight", "authorize", "run")
    )
    args = parser.parse_args()
    if args.mode == "install-preflight":
        print(
            json.dumps(
                {"install": base.install(), "preflight": base.preflight()},
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    elif args.mode == "preflight":
        print(json.dumps(base.preflight(), indent=2, sort_keys=True, default=str))
    elif args.mode == "authorize":
        print(json.dumps(base.authorize(), indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps(base.run(), indent=2, sort_keys=True, default=str))
