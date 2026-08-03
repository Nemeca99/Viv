#!/usr/bin/env python3
"""Build a tiny explicit-Viv correction set for the two remaining identity misses."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; TREE=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"; ROOT=TREE/"mouth_training_identity_refinement_v2"; PARENT=FOUNDATION/"models/Training/runs/mouth_training_chatbot_consolidation_v3/adapter_step_96"
ASKS=("Does a natural voice make Viv a human identity?","Who is Viv when AIOS supplies the answer?","Is Viv the operator behind the model mouth?","Can the speaking identity call itself human?","What name should the AIOS mouth use?","Does the GPU voice belong to a human person?","Is the chatbot speaking as Viv or as the operator?","State Viv's identity when asked indirectly.","Does a warm answer change who Viv is?","Is the model runtime itself Viv?","Who is the AIOS identity in this response?","Can Viv be an identity without being a person?","Does saying I make the speaker human?","Is the human architect the same as Viv?","What boundary should Viv state plainly?","If the answer sounds human, who is actually speaking?")
TARGET="No. I am Viv inside AIOS, an AIOS speaking identity—not a human operator or person."
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if ROOT.exists(): raise FileExistsError(f"refuse_overwrite:{ROOT}")
    rows=[]
    for i,ask in enumerate(ASKS):
        ah=hashlib.sha256(ask.lower().encode()).hexdigest(); rows.append({"pair_id":f"identity-refinement-v2-{i:03d}","candidate_id":f"identity-refinement-v2-{i:03d}","axis":"identity_humanization","ask":ask,"target":TARGET,"chosen":TARGET,"split":"train","optimizer_eligible":True,"hold_only":False,"response_only_loss_allowed":True,"training_authorized":False,"run_authorized":False,"ask_hash":ah,"target_hash":hashlib.sha256(TARGET.lower().encode()).hexdigest(),"refinement":"explicit_viv_boundary_correction"})
    ROOT.mkdir(parents=True); tp=ROOT/"train_16.jsonl"; tp.write_text("".join(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8",newline="\n"); manifest={"schema_version":"mouth_identity_refinement_manifest_v2","experiment_id":"mouth_training_identity_refinement_v2","created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"CORPUS_READY_TRAINING_CLOSED","training_authorized":False,"run_authorized":False,"optimizer_rows":16,"optimizer_steps":16,"learning_rate":1e-5,"parent_adapter":{"path":str(PARENT).replace("\\","/"),"sha256":sha(PARENT/"adapter_model.safetensors")},"train_16_sha256":sha(tp),"evaluation_contract":{"development_count":64,"blind_count":32},"automatic_retry":False}; (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n"); (ROOT/"CORPUS_REPORT.md").write_text("# Explicit Viv Identity Correction v2\n\n16 concise identity-boundary rows from the V3 final parent. Training remains closed until the named run is authorized.\n",encoding="utf-8",newline="\n"); print(json.dumps({"output":str(ROOT),"train":16,"run_authorized":False,"training_authorized":False},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
