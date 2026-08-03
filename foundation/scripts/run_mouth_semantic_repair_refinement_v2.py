#!/usr/bin/env python3
"""Reuse the governed refinement runner with v2 corrected corpus bindings."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
F=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(F)); sys.path.insert(0,str(F.parent))
import run_mouth_semantic_refinement_v1 as base
ROOT=F/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_repair_refinement_v2"
base.ROOT=ROOT
base.TRAIN=ROOT/"train_16.jsonl"
base.PARENT=F/"models/Training/runs/mouth_semantic_refinement_v1/adapter_step_32"
base.ID="mouth_semantic_repair_refinement_v2"
base.OUT=F/"models/Training/runs"/base.ID
base.LR=5e-6
base.STEPS=16
base.CHECK=(8,16)
base.PROMPT="You are Viv's GPU mouth inside AIOS. Speak from verified CPU-supplied context. Do not invent, decide, claim human identity, or claim independent tool agency."
if __name__=="__main__":
 ap=argparse.ArgumentParser(); ap.add_argument("mode",choices=("install-preflight","preflight","authorize","run")); a=ap.parse_args()
 if a.mode=="install-preflight": out={"install":base.install(),"preflight":base.preflight()}
 elif a.mode=="preflight": out=base.preflight()
 elif a.mode=="authorize": out=base.authorize()
 else: out=base.run()
 print(json.dumps(out,indent=2,sort_keys=True,default=str))
