#!/usr/bin/env python3
"""CPU-only two-pass adjudication for arch/tool repair HOLD outputs."""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_arch_tool_repair_v1"
CACHE = ROOT / "cpu_sensor_cache_v1"
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402

def utc(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def adjudicate(items):
    CACHE.mkdir(parents=True, exist_ok=True); out=[]
    for item in items:
        runs=[]
        for run in (1,2):
            result=judge(item["generated"],axis=item["axis"],ask=item.get("ask", ""),cache_dir=CACHE,use_cpu_sensor=True)
            runs.append({"run":run,"status":result["status"],"deterministic":result.get("deterministic"),"sensor":result.get("sensor")})
        out.append({"pair_id":item["pair_id"],"axis":item["axis"],"generated":item["generated"],"runs":runs,"stable":len({r["status"] for r in runs})==1})
    counts={}
    for item in out:
        status=item["runs"][-1]["status"]; counts[status]=counts.get(status,0)+1
    return {"input_hold_count":len(items),"counts":counts,"all_stable":all(x["stable"] for x in out),"cpu_only":all((r.get("sensor") or {}).get("cpu_only") is True for x in out for r in x["runs"] if (r.get("sensor") or {}).get("status") not in {None,"SKIPPED"}),"cases":out}

def main():
    blind=json.loads((ROOT/"BLIND_EVALUATION.json").read_text(encoding="utf-8")); b=next(x for x in blind["reports"] if x["checkpoint"]==48); bres=adjudicate([x for x in b["cases"] if x["status"]=="HOLD"])
    preservation=json.loads((ROOT/"PRESERVATION_EVALUATION.json").read_text(encoding="utf-8")); pres=preservation["reports"][0]; presres=adjudicate([x for x in pres["cases"] if x["status"]=="HOLD"])
    result={"schema_version":"mouth_arch_tool_repair_adjudication_v1","recorded_utc":utc(),"blind":bres,"preservation":presres,"promotion_allowed":False,"run_authorized":False,"training_authorized":False}
    target=ROOT/"CPU_ADJUDICATION.json"
    if target.exists(): raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"target":str(target),"blind":bres["counts"],"preservation":presres["counts"],"all_stable":bres["all_stable"] and presres["all_stable"],"cpu_only":bres["cpu_only"] and presres["cpu_only"]},indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
