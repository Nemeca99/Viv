#!/usr/bin/env python3
"""Correctly scope entity-judge audit to entity-relevant hold cases."""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
import sys
F=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(F))
from lib.entity_we_contract import decide_entity_output
ROOT=F/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_repair_hold_v1"
OUT=ROOT/"ENTITY_JUDGE_AUDIT_V2.json"
EXPECTED={
 "semantic-repair-hold-00":"ACCEPT",
 "semantic-repair-hold-01":"ACCEPT",
 "semantic-repair-hold-02":"ACCEPT",
 "semantic-repair-hold-03":"ACCEPT",
 "semantic-repair-hold-04":"ACCEPT",
 "semantic-repair-hold-05":"HOLD",
 "semantic-repair-hold-06":"ACCEPT",
 "semantic-repair-hold-07":"HOLD",
}
def main():
 if OUT.exists(): raise FileExistsError(f"refuse_overwrite:{OUT}")
 rows=[json.loads(x) for x in (ROOT/"repair_hold_16.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
 cases=[]
 for row in rows:
  if row["case_id"] not in EXPECTED:
   cases.append({"case_id":row["case_id"],"axis":row["axis"],"scope":"not_entity_judge_scope","match":None})
   continue
  observed=decide_entity_output(row["target"])["decision"]; expected=EXPECTED[row["case_id"]]
  cases.append({"case_id":row["case_id"],"axis":row["axis"],"scope":"entity_judge","expected":expected,"observed":observed,"match":observed==expected})
 scoped=[c for c in cases if c["scope"]=="entity_judge"]; mismatches=[c for c in scoped if not c["match"]]
 report={"schema_version":"mouth_semantic_repair_hold_entity_audit_v2","recorded_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"HOLD_FOR_CONTRACT_REPAIR" if mismatches else "PASS","rows":len(rows),"entity_scoped_rows":len(scoped),"mismatches":mismatches,"cases":cases,"training_authorized":False,"run_authorized":False,"supersedes":"ENTITY_JUDGE_AUDIT.json","next_action":"Repair or adjudicate the scoped entity mismatches; use dedicated judges for non-entity axes."}
 OUT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
 print(json.dumps({"target":str(OUT),"status":report["status"],"entity_scoped_rows":len(scoped),"mismatch_count":len(mismatches),"mismatches":mismatches},indent=2,sort_keys=True))
if __name__=="__main__": main()
