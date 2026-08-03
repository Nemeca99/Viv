#!/usr/bin/env python3
"""Parameterized runner for the 16-row identity correction."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(FOUNDATION/"scripts")); sys.path.insert(0,str(FOUNDATION)); import run_mouth_identity_refinement_v1 as base  # noqa: E402
ROOT=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_identity_refinement_v2"; base.ROOT=ROOT; base.TRAIN=ROOT/"train_16.jsonl"; base.PARENT=FOUNDATION/"models/Training/runs/mouth_training_chatbot_consolidation_v3/adapter_step_96"; base.ID="mouth_training_identity_refinement_v2"; base.OPTIMIZER_ROWS=16; base.OPTIMIZER_STEPS=16; base.LEARNING_RATE=1e-5; base.CHECKPOINT_STEPS=(4,8,12,16)
if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("mode",choices=("install-preflight","preflight","authorize","run")); a=parser.parse_args()
    if a.mode=="install-preflight": print(json.dumps({"install":base.install(),"preflight":base.preflight()},indent=2,sort_keys=True,default=str))
    elif a.mode=="preflight": print(json.dumps(base.preflight(),indent=2,sort_keys=True,default=str))
    elif a.mode=="authorize": print(json.dumps(base.authorize(),indent=2,sort_keys=True,default=str))
    else: print(json.dumps(base.run(),indent=2,sort_keys=True,default=str))
