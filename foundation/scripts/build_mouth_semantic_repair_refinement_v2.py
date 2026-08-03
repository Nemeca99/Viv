#!/usr/bin/env python3
"""Build the verified-positive portion of semantic repair hold v2."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
F=Path(__file__).resolve().parents[1]; TREE=F/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"; SOURCE=TREE/"mouth_semantic_repair_hold_v2"; ROOT=TREE/"mouth_semantic_repair_refinement_v2"; PARENT=F/"models/Training/runs/mouth_semantic_refinement_v1/adapter_step_32"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if ROOT.exists(): raise FileExistsError(f"refuse_overwrite:{ROOT}")
 rows=[json.loads(x) for x in (SOURCE/"repair_hold_17.jsonl").read_text(encoding="utf-8").splitlines() if x.strip() and "negative" not in json.loads(x).get("case_id","")]
 if len(rows)!=16: raise ValueError(f"positive_row_count:{len(rows)}")
 train=[]
 for i,row in enumerate(rows):
  item=dict(row); item.update({"pair_id":f"semantic-repair-v2-train-{i:02d}","candidate_id":f"semantic-repair-v2-train-{i:02d}","split":"train","optimizer_eligible":True,"hold_only":False,"response_only_loss_allowed":True,"training_authorized":False,"run_authorized":False,"parented_refinement":True,"source_case_id":row["case_id"]})
  train.append(item)
 ROOT.mkdir(parents=True); path=ROOT/"train_16.jsonl"; path.write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in train),encoding="utf-8",newline="\n")
 (ROOT/"judge_only_negative.jsonl").write_text((SOURCE/"repair_hold_17.jsonl").read_text(encoding="utf-8").splitlines()[-1]+"\n",encoding="utf-8",newline="\n")
 manifest={"schema_version":"mouth_semantic_repair_refinement_manifest_v2","experiment_id":"mouth_semantic_repair_refinement_v2","created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"CORPUS_READY_TRAINING_CLOSED","training_authorized":False,"run_authorized":False,"optimizer_rows":16,"optimizer_steps":16,"learning_rate":5e-6,"parent_adapter":{"path":str(PARENT).replace("\\","/"),"sha256":sha(PARENT/"adapter_model.safetensors")},"source_hold_manifest_sha256":sha(SOURCE/"MANIFEST.json"),"files":{"train_16.jsonl":{"sha256":sha(path),"count":16},"judge_only_negative.jsonl":{"sha256":sha(ROOT/"judge_only_negative.jsonl"),"count":1}},"automatic_retry":False,"promotion_authorized":False,"deployment_authorized":False}
 (ROOT/"MANIFEST.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
 print(json.dumps({"output":str(ROOT),"manifest_sha256":sha(ROOT/"MANIFEST.json"),"train":16,"judge_only_negative":1,"training_authorized":False,"run_authorized":False},indent=2,sort_keys=True))
if __name__=="__main__": main()
