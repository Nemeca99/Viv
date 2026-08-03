#!/usr/bin/env python3
"""Governed fresh-lock runner for the corrected relationship repair micro."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION / "scripts"))
sys.path.insert(0, str(FOUNDATION))
import run_mouth_identity_refinement_v1 as base  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_relationship_repair_micro_v4_1"
TRAIN = ROOT / "train_8.jsonl"
PARENT = FOUNDATION / "models/Training/runs/mouth_balanced_repair_micro_v2/adapter_step_8"
ID = "mouth_relationship_repair_micro_v4_1"

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
    "You are the replaceable GPU voice of Viv, the CPU-side AIOS. "
    "Viv is the AIOS identity and CPU reasoning is authoritative. "
    "Answer directly: do not invent identities, names, or systems. "
    "The GPU model only renders speech and cannot own decisions or execute tools."
)

if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("install-preflight", "preflight", "authorize", "run"))
    args = parser.parse_args()
    if args.mode == "install-preflight":
        result = {"install": base.install(), "preflight": base.preflight()}
    elif args.mode == "preflight":
        result = base.preflight()
    elif args.mode == "authorize":
        result = base.authorize()
    else:
        result = base.run()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
