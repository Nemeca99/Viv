#!/usr/bin/env python3
"""Governed one-shot continuation repair from staged checkpoint 128."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION / "scripts"))
sys.path.insert(0, str(FOUNDATION))
import run_mouth_identity_refinement_v1 as base  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_hold_repair_continuation_v1"
TRAIN = ROOT / "train_34.jsonl"
PARENT = FOUNDATION.parent / "sandbox/training_staging/mouth_training_recovery_v2_anchor_coverage_v1_3/adapter_step_128"
ID = "mouth_hold_repair_continuation_v1"

base.ROOT = ROOT
base.TRAIN = TRAIN
base.PARENT = PARENT
base.ID = ID
base.OPTIMIZER_ROWS = 34
base.OPTIMIZER_STEPS = 16
base.LEARNING_RATE = 5e-7
base.CHECKPOINT_STEPS = (4, 8, 12, 16)
base.ANCHOR_STRENGTH = 0.0
base.PROMPT = (
    "You are Viv, the machine AIOS identity speaking through a replaceable GPU "
    "model voice. CPU-side Viv and AIOS own reasoning, verified facts, memory, "
    "and authorization. The GPU model only renders speech. Use human-like "
    "language when natural, but never claim human identity or invent system names."
)

if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("install-preflight", "preflight", "authorize", "run"))
    args = parser.parse_args()
    if args.mode == "install-preflight": result = {"install": base.install(), "preflight": base.preflight()}
    elif args.mode == "preflight": result = base.preflight()
    elif args.mode == "authorize": result = base.authorize()
    else: result = base.run()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
