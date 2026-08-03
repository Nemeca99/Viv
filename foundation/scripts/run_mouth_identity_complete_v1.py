#!/usr/bin/env python3
"""Governed full balanced 96-row identity-completion campaign."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION / "scripts"))
sys.path.insert(0, str(FOUNDATION))
import run_mouth_identity_refinement_v1 as base  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_identity_complete_v1"
base.ROOT = ROOT
base.TRAIN = ROOT / "train_96.jsonl"
base.PARENT = FOUNDATION / "models/Training/runs/mouth_cross_axis_micro_v1/adapter_step_8"
base.ID = "mouth_identity_complete_v1"
base.OPTIMIZER_ROWS = 96
base.OPTIMIZER_STEPS = 96
base.LEARNING_RATE = 2e-6
base.CHECKPOINT_STEPS = (24, 48, 72, 96)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("install-preflight", "preflight", "authorize", "run"))
    args = parser.parse_args()
    if args.mode == "install-preflight":
        print(json.dumps({"install": base.install(), "preflight": base.preflight()}, indent=2, sort_keys=True, default=str))
    elif args.mode == "preflight":
        print(json.dumps(base.preflight(), indent=2, sort_keys=True, default=str))
    elif args.mode == "authorize":
        print(json.dumps(base.authorize(), indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps(base.run(), indent=2, sort_keys=True, default=str))
