"""Audit acronym-surface regression v4."""
from __future__ import annotations
import hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import sys
F=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(F.parent)); from voice_core.acronym_registry import repair_acronym_usage  # noqa: E402
ROOT=F/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_acronym_surface_regression_v4"; SRC=ROOT/"regression_48.jsonl"; OUT=ROOT/"REGRESSION_EVALUATION.json"
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->int:
 if OUT.exists(): raise FileExistsError(f"refuse_overwrite:{OUT}")
 rows=[json.loads(x) for x in SRC.read_text(encoding="utf-8").splitlines() if x.strip()]; cases=[]
 for r in rows:
  x=repair_acronym_usage(r["text"]); obs="REPAIRED_PASS" if x["pass"] and x["changed"] else "CLEAN_PASS" if x["pass"] else "UNRESOLVED_HOLD"; cases.append({"case_id":r["case_id"],"expected":r["expected"],"observed":obs,"match":obs==r["expected"],"text":r["text"],"repaired":x["repaired"],"repairs":x["repairs"],"unresolved":x["unresolved"]})
 mism=[c["case_id"] for c in cases if not c["match"]]; counts=Counter(c["observed"] for c in cases); report={"schema_version":"mouth_acronym_surface_regression_evaluation_v4","recorded_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"REGRESSION_PASS" if not mism else "REGRESSION_MISMATCH","source_jsonl_sha256":sha(SRC),"rows":48,"matched":48-len(mism),"mismatches":mism,"observed_counts":dict(sorted(counts.items())),"cases":cases,"optimizer_eligible_any":False,"training_authorized":False,"run_authorized":False}; OUT.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n"); print(json.dumps({"target":str(OUT),"status":report["status"],"rows":48,"matched":report["matched"],"mismatches":mism,"observed_counts":report["observed_counts"],"training_authorized":False,"run_authorized":False},indent=2,sort_keys=True)); return 0 if not mism else 1
if __name__=="__main__": raise SystemExit(main())
