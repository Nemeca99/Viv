#!/usr/bin/env python3
"""Governed one-shot final explicit-relationship repair."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(FOUNDATION/'scripts')); sys.path.insert(0,str(FOUNDATION))
import run_mouth_identity_refinement_v1 as base
ROOT=FOUNDATION/'artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_final_hold_repair_v1'; TRAIN=ROOT/'train_22.jsonl'; PARENT=FOUNDATION/'models/Training/runs/mouth_hold_repair_continuation_v1/adapter_step_4'; ID='mouth_final_hold_repair_v1'
base.ROOT=ROOT; base.TRAIN=TRAIN; base.PARENT=PARENT; base.ID=ID; base.OPTIMIZER_ROWS=22; base.OPTIMIZER_STEPS=8; base.LEARNING_RATE=2e-7; base.CHECKPOINT_STEPS=(2,4,6,8); base.ANCHOR_STRENGTH=0.0
base.PROMPT='You are Viv, the machine AIOS identity speaking through a replaceable GPU model voice. CPU-side Viv and AIOS own reasoning and authority; the GPU model only renders speech. State Viv and AIOS explicitly when asked who is speaking. Human-like language is allowed, but never claim human identity or invent system names.'
if __name__=='__main__':
 ROOT.mkdir(parents=True,exist_ok=True); p=argparse.ArgumentParser(); p.add_argument('mode',choices=('install-preflight','preflight','authorize','run')); a=p.parse_args(); result={'install':base.install(),'preflight':base.preflight()} if a.mode=='install-preflight' else base.preflight() if a.mode=='preflight' else base.authorize() if a.mode=='authorize' else base.run(); print(json.dumps(result,indent=2,sort_keys=True,default=str))
