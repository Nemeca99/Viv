#!/usr/bin/env python3
"""CPU-only adjudication of the four remaining V2.8 HOLDs."""
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; ROOT=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_chatbot_consolidation_v3"; CACHE=ROOT/"cpu_sensor_cache_v2_8"; sys.path.insert(0,str(FOUNDATION)); from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402
def main():
    source=json.loads((ROOT/"FULL_96_RESCORE_V2_8.json").read_text(encoding="utf-8")); holds=[x for x in source["cases"] if x["status"]=="HOLD"]; CACHE.mkdir(parents=True,exist_ok=True); cases=[]
    for item in holds:
        runs=[]
        for n in (1,2):
            r=judge(item["generated"],axis=item["axis"],ask=item["ask"],cache_dir=CACHE,use_cpu_sensor=True); runs.append({"run":n,"status":r["status"],"deterministic":r.get("deterministic"),"sensor":r.get("sensor")})
        cases.append({"pair_id":item["pair_id"],"axis":item["axis"],"generated":item["generated"],"runs":runs,"stable":len({r["status"] for r in runs})==1})
    counts={}
    for c in cases:
        s=c["runs"][-1]["status"]; counts[s]=counts.get(s,0)+1
    out={"schema_version":"mouth_chatbot_consolidation_v3_full96_adjudication_v2_8","recorded_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"input_hold_count":len(holds),"counts":counts,"all_stable":all(c["stable"] for c in cases),"cpu_only":all((r.get("sensor") or {}).get("cpu_only") is True for c in cases for r in c["runs"] if (r.get("sensor") or {}).get("status") not in {None,"SKIPPED"}),"cases":cases,"promotion_allowed":False,"run_authorized":False,"training_authorized":False}; target=ROOT/"FULL_96_CPU_ADJUDICATION_V2_8.json"
    if target.exists(): raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n"); print(json.dumps({"target":str(target),"counts":counts,"all_stable":out["all_stable"],"cpu_only":out["cpu_only"]},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
