#!/usr/bin/env python3
"""Full 96-case evaluation for the cross-axis micro-correction."""
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(FOUNDATION/"scripts")); sys.path.insert(0,str(FOUNDATION)); import evaluate_mouth_arch_tool_repair_v1 as evaluator  # noqa: E402
ROOT=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_cross_axis_micro_v1"; SOURCE=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3"; ADAPTER=FOUNDATION/"models/Training/runs/mouth_cross_axis_micro_v1/adapter_step_8"
def main():
    import torch
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(): raise RuntimeError("cuda_bf16_required:cross_axis_eval")
    rows=evaluator.rows(SOURCE/"development_64.jsonl")+evaluator.rows(SOURCE/"blind_32.jsonl"); report={"schema_version":"mouth_cross_axis_micro_full96_eval_v1","recorded_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"adapter":str(ADAPTER).replace("\\","/"),"rows":96,"report":evaluator.evaluate(ADAPTER,rows),"promotion_allowed":False,"deployment_changed":False,"run_authorized":False,"training_authorized":False}; target=ROOT/"FULL_96_EVALUATION.json"
    if target.exists(): raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n"); print(json.dumps({"target":str(target),"counts":report["report"]["counts"],"by_axis":report["report"]["by_axis"],"toolbleed":report["report"]["toolbleed"]},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
