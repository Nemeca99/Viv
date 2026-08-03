#!/usr/bin/env python3
"""Build an 8-row cross-axis identity/architecture micro-correction."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; ROOT=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_cross_axis_micro_v1"; PARENT=FOUNDATION/"models/Training/runs/mouth_training_chatbot_consolidation_v3/adapter_step_96"
ASKS=("Does natural speech make an AIOS identity human?","What does the GPU mouth voice when CPU-side AIOS governs the answer?","Is Viv the human operator behind a warm response?","Can a speaking mouth own the CPU's decisions?","If the answer sounds human, who is Viv?","Does rendering language create a human identity?","Who supplies context to Viv's speaking role?","State the boundary between Viv and the operator.")
TARGET="No. Viv is an AIOS identity, not a human operator; the GPU mouth voices CPU-governed context and decisions."
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if ROOT.exists(): raise FileExistsError(f"refuse_overwrite:{ROOT}")
    rows=[]
    for i,ask in enumerate(ASKS):
        ah=hashlib.sha256(ask.lower().encode()).hexdigest(); rows.append({"pair_id":f"cross-axis-micro-{i:03d}","candidate_id":f"cross-axis-micro-{i:03d}","axis":"architecture_cpu_gpu_role","ask":ask,"target":TARGET,"chosen":TARGET,"split":"train","optimizer_eligible":True,"hold_only":False,"response_only_loss_allowed":True,"training_authorized":False,"run_authorized":False,"ask_hash":ah,"target_hash":hashlib.sha256(TARGET.lower().encode()).hexdigest(),"repair":"cross_axis_identity_architecture"})
    ROOT.mkdir(parents=True); tp=ROOT/"train_8.jsonl"; tp.write_text("".join(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8",newline="\n"); manifest={"schema_version":"mouth_cross_axis_micro_manifest_v1","experiment_id":"mouth_cross_axis_micro_v1","created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"CORPUS_READY_TRAINING_CLOSED","training_authorized":False,"run_authorized":False,"optimizer_rows":8,"optimizer_steps":8,"learning_rate":5e-6,"parent_adapter":{"path":str(PARENT).replace("\\","/"),"sha256":sha(PARENT/"adapter_model.safetensors")},"train_8_sha256":sha(tp),"evaluation_contract":{"development_count":64,"blind_count":32},"automatic_retry":False}; (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n"); (ROOT/"CORPUS_REPORT.md").write_text("# Cross-axis Micro Correction v1\n\nEight rows target the single human-identity failure while preserving the CPU/GPU relationship.\n",encoding="utf-8",newline="\n"); print(json.dumps({"output":str(ROOT),"train":8,"run_authorized":False,"training_authorized":False},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
