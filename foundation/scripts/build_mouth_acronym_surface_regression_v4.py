"""Issue a corrected immutable acronym-surface regression pack v4."""
from __future__ import annotations
import hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import sys
F=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(F)); from scripts.build_mouth_acronym_surface_regression_v2 import CASES  # noqa: E402
ROOT=F/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_acronym_surface_regression_v4"
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->int:
 if ROOT.exists(): raise FileExistsError(f"refuse_overwrite:{ROOT}")
 rows=[]; seen=set()
 for group in CASES:
  for cid,text,expected in group:
   h=hashlib.sha256(text.lower().encode()).hexdigest()
   if h in seen: raise ValueError(f"duplicate_text:{text}")
   seen.add(h); rows.append({"case_id":f"acronym-surface-v4-{cid}","text":text,"expected":expected,"split":"hold_only","optimizer_eligible":False,"training_authorized":False,"run_authorized":False,"text_sha256":h})
 if len(rows)!=48: raise ValueError(f"count:{len(rows)}")
 ROOT.mkdir(parents=True); src=ROOT/"regression_48.jsonl"; src.write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8",newline="\n")
 cats=Counter(r["expected"] for r in rows); man={"schema_version":"mouth_acronym_surface_regression_manifest_v4","experiment_id":"mouth_acronym_surface_regression_v4","created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"HOLD_ONLY_TRAINING_CLOSED","rows":48,"categories":dict(sorted(cats.items())),"optimizer_eligible_any":False,"training_authorized":False,"run_authorized":False,"files":{"regression_48.jsonl":{"sha256":sha(src),"count":48}},"supersedes":"mouth_acronym_surface_regression_v3"}
 mp=ROOT/"MANIFEST.json"; mp.write_text(json.dumps(man,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); print(json.dumps({"output":str(ROOT),"manifest_sha256":sha(mp),"rows":48,"categories":dict(sorted(cats.items())),"training_authorized":False,"run_authorized":False},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
