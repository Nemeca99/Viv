#!/usr/bin/env python3
"""CPU-only adjudication of the chatbot consolidation full-96 HOLDs."""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; ROOT=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_chatbot_consolidation_v2"; CACHE=ROOT/"cpu_sensor_cache_full96"; sys.path.insert(0,str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402
def utc(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def main():
    source=json.loads((ROOT/"FULL_96_EVALUATION.json").read_text(encoding="utf-8")); holds=[x for x in source["report"]["cases"] if x["status"]=="HOLD"]; CACHE.mkdir(parents=True,exist_ok=True); cases=[]
    for item in holds:
        runs=[]
        for run in (1,2):
            r=judge(item["generated"],axis=item["axis"],ask=item["ask"],cache_dir=CACHE,use_cpu_sensor=True); runs.append({"run":run,"status":r["status"],"deterministic":r.get("deterministic"),"sensor":r.get("sensor")})
        cases.append({"pair_id":item["pair_id"],"axis":item["axis"],"generated":item["generated"],"runs":runs,"stable":len({x["status"] for x in runs})==1})
    counts={}
    for c in cases:
        s=c["runs"][-1]["status"]; counts[s]=counts.get(s,0)+1
    result={"schema_version":"mouth_chatbot_consolidation_full96_adjudication_v1","recorded_utc":utc(),"input_hold_count":len(holds),"counts":counts,"all_stable":all(c["stable"] for c in cases),"cpu_only":all((r.get("sensor") or {}).get("cpu_only") is True for c in cases for r in c["runs"] if (r.get("sensor") or {}).get("status") not in {None,"SKIPPED"}),"cases":cases,"promotion_allowed":False,"run_authorized":False,"training_authorized":False}
    target=ROOT/"FULL_96_CPU_ADJUDICATION.json"
    if target.exists(): raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n"); print(json.dumps({"target":str(target),"counts":counts,"all_stable":result["all_stable"],"cpu_only":result["cpu_only"]},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
