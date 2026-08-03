#!/usr/bin/env python3
"""Long-window execution wrapper for chatbot consolidation v2."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

FOUNDATION=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(FOUNDATION)); sys.path.insert(0,str(FOUNDATION/"scripts"))
import run_mouth_chatbot_consolidation_v1 as base  # noqa: E402

ROOT=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_chatbot_consolidation_v2"
base.ROOT=ROOT; base.TRAIN=ROOT/"train_96.jsonl"; base.EXPERIMENT_ID="mouth_training_chatbot_consolidation_v2"

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("mode",choices=("install-preflight","preflight","authorize","run")); args=parser.parse_args()
    if args.mode=="install-preflight": print(json.dumps({"install":base.install(),"preflight":base.preflight()},indent=2,sort_keys=True,default=str))
    elif args.mode=="preflight": print(json.dumps(base.preflight(),indent=2,sort_keys=True,default=str))
    elif args.mode=="authorize": print(json.dumps(base.authorize(),indent=2,sort_keys=True,default=str))
    else: print(json.dumps(base.run(),indent=2,sort_keys=True,default=str))
