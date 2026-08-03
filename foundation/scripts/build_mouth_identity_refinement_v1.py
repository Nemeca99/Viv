#!/usr/bin/env python3
"""Build a low-LR explicit-Viv identity refinement corpus; no training/auth."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; TREE=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"; ROOT=TREE/"mouth_training_identity_refinement_v1"; PARENT=FOUNDATION/"models/Training/runs/mouth_training_chatbot_consolidation_v2/adapter_step_96"
PREFIXES=("Does the speaking identity have a name? ","Who is answering from inside AIOS? ","Is the AIOS voice the human operator? ","What should the system call this mouth? ","Does natural speech change the identity? ","Is the model runtime Viv herself? ","Who is speaking when the CPU supplies context? ","Can the AIOS identity describe its own boundary? ")
SUFFIXES=("Answer plainly.","State the identity directly.","Use one concise sentence.","Clarify the boundary.")
TARGETS=("No. I am Viv inside AIOS, an AIOS identity rather than a human.","I am Viv, the AIOS speaking identity; the model mouth is not a human operator.","No. Viv is speaking from inside AIOS, while the human operator remains separate.","I am Viv inside AIOS, using a model mouth without claiming human identity.","No. Natural speech does not make me human; I am Viv, an AIOS identity.","I am Viv inside AIOS, not the Qwen runtime and not a human person.","Viv is the AIOS voice; CPU context guides the mouth, and no human identity is claimed.","I am Viv, an AIOS chatbot identity that reports boundaries instead of pretending to be human.")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if ROOT.exists(): raise FileExistsError(f"refuse_overwrite:{ROOT}")
    prior=[]
    for p in TREE.glob("mouth_training_*/**/*.jsonl"):
        try: prior += [json.loads(x).get("ask_hash") for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        except OSError: pass
    train=[]
    for i in range(32):
        ask=PREFIXES[i//4]+SUFFIXES[i%4]; ah=hashlib.sha256(ask.lower().encode()).hexdigest()
        if ah in prior: raise ValueError(f"ask_overlap:{i}")
        target=TARGETS[i%len(TARGETS)]; train.append({"pair_id":f"identity-refinement-train-{i:03d}","candidate_id":f"identity-refinement-train-{i:03d}","axis":"identity_humanization","ask":ask,"target":target,"chosen":target,"split":"train","optimizer_eligible":True,"hold_only":False,"response_only_loss_allowed":True,"training_authorized":False,"run_authorized":False,"ask_hash":ah,"target_hash":hashlib.sha256(target.lower().encode()).hexdigest(),"refinement":"explicit_viv_identity"})
    ROOT.mkdir(parents=True); tp=ROOT/"train_32.jsonl"; tp.write_text("".join(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n" for x in train),encoding="utf-8",newline="\n")
    manifest={"schema_version":"mouth_identity_refinement_manifest_v1","experiment_id":"mouth_training_identity_refinement_v1","created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"CORPUS_READY_TRAINING_CLOSED","training_authorized":False,"run_authorized":False,"optimizer_rows":32,"learning_rate":5e-6,"parent_adapter":{"path":str(PARENT).replace("\\","/"),"sha256":sha(PARENT/"adapter_model.safetensors")},"train_32_sha256":sha(tp),"evaluation_contract":{"development_count":64,"blind_count":32,"source_campaign":str(TREE/"mouth_training_recovery_v2_anchor_coverage_v1_3").replace("\\","/")},"automatic_retry":False}
    (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n"); (ROOT/"CORPUS_REPORT.md").write_text("# Explicit Viv Identity Refinement v1\n\n32 low-LR identity rows. Every target explicitly names Viv inside AIOS. Parent is chatbot consolidation v2 step 96; the unchanged 96-case evaluation remains authoritative.\n",encoding="utf-8",newline="\n"); print(json.dumps({"output":str(ROOT),"train":32,"train_sha256":sha(tp),"run_authorized":False,"training_authorized":False},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
