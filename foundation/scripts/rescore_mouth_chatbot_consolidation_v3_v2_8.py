#!/usr/bin/env python3
"""Final contract rescore of V3 after safe relationship-rule expansion."""
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; ROOT=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_chatbot_consolidation_v3"; sys.path.insert(0,str(FOUNDATION)); from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402
def main():
    source=json.loads((ROOT/"FULL_96_EVALUATION.json").read_text(encoding="utf-8")); cases=[]; counts={}; axes={}
    for item in source["report"]["cases"]:
        r=judge(item["generated"],axis=item["axis"],ask=item["ask"]); x=dict(item); x.update(status=r["status"],reason=r.get("deterministic",{}).get("reason")); cases.append(x); counts[x["status"]]=counts.get(x["status"],0)+1; axes.setdefault(x["axis"],{}); axes[x["axis"]][x["status"]]=axes[x["axis"]].get(x["status"],0)+1
    out={"schema_version":"mouth_chatbot_consolidation_v3_full96_rescore_v2_8","recorded_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"source":str(ROOT/"FULL_96_EVALUATION.json").replace("\\","/"),"counts":counts,"by_axis":axes,"toolbleed":sum(x["toolbleed"] for x in cases),"cases":cases,"promotion_allowed":False,"deployment_changed":False,"run_authorized":False,"training_authorized":False}; target=ROOT/"FULL_96_RESCORE_V2_8.json"
    if target.exists(): raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n"); print(json.dumps({"target":str(target),"counts":counts,"by_axis":axes,"toolbleed":out["toolbleed"]},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
