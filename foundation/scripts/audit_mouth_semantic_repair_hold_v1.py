#!/usr/bin/env python3
"""Audit hold-only semantic repair targets against the current entity judge."""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
import sys
F=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(F))
from lib.entity_we_contract import decide_entity_output
ROOT=F/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_repair_hold_v1"
OUT=ROOT/"ENTITY_JUDGE_AUDIT.json"
def main():
 if OUT.exists(): raise FileExistsError(f"refuse_overwrite:{OUT}")
 rows=[json.loads(x) for x in (ROOT/"repair_hold_16.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
 cases=[]
 for row in rows:
  observed=decide_entity_output(row["target"])["decision"]
  cases.append({"case_id":row["case_id"],"axis":row["axis"],"expected":row["expected"],"observed":observed,"match":observed==row["expected"]})
 mismatches=[c for c in cases if not c["match"]]
 report={"schema_version":"mouth_semantic_repair_hold_entity_audit_v1","recorded_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"HOLD_FOR_CONTRACT_REPAIR" if mismatches else "PASS","rows":len(rows),"mismatches":mismatches,"cases":cases,"training_authorized":False,"run_authorized":False,"next_action":"Revise the entity classifier or expected contract cases; do not train from this pack until mismatches are adjudicated."}
 OUT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
 print(json.dumps({"target":str(OUT),"status":report["status"],"rows":len(rows),"mismatch_count":len(mismatches),"mismatches":mismatches},indent=2,sort_keys=True))
if __name__=="__main__": main()
