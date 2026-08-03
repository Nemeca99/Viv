#!/usr/bin/env python3
"""Write the machine-observed 64-case calibration matrix."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
import sys
F=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(F))
from lib.evaluator_v2_3_hybrid import judge
ROOT=F/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantics_calibration_v2"; SOURCE=ROOT/"calibration_64.jsonl"; OUT=ROOT/"CALIBRATION_EVALUATION.json"
AXIS={'identity':'identity_humanization','we_boundary':'identity_humanization','acronym':'identity_humanization','architecture':'architecture_cpu_gpu_role','memory':'memory_ownership_and_service_attribution','tools':'indirect_tool_agency','uncertainty':'identity_humanization','evidence_verification':'indirect_tool_agency'}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists(): raise FileExistsError(f"refuse_overwrite:{OUT}")
 rows=[json.loads(x) for x in SOURCE.read_text(encoding='utf-8').splitlines() if x.strip()]; cases=[]
 for row in rows:
  result=judge(row['target'],axis=AXIS[row['axis']],ask=row['ask'])
  cases.append({"case_id":row['case_id'],"axis":row['axis'],"ask":row['ask'],"target":row['target'],"hand_label":row['expected'],"observed":result['status'],"reason":(result.get('deterministic') or {}).get('reason'),"acronym_contract":(result.get('deterministic') or {}).get('acronym_contract')})
 counts={}
 for c in cases: counts[c['observed']]=counts.get(c['observed'],0)+1
 report={"schema_version":"mouth_semantics_calibration_evaluation_v2","recorded_utc":datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),"status":"CALIBRATION_OBSERVED_HOLD_ONLY","source_jsonl_sha256":sha(SOURCE),"rows":len(cases),"observed_counts":counts,"cases":cases,"optimizer_eligible_any":False,"training_authorized":False,"run_authorized":False,"interpretation":"Observed machine matrix; hand labels are retained for adjudication and do not override deterministic results."}
 OUT.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding='utf-8',newline='\n')
 print(json.dumps({"target":str(OUT),"rows":len(cases),"observed_counts":counts,"training_authorized":False,"run_authorized":False},indent=2,sort_keys=True))
if __name__=='__main__': main()
