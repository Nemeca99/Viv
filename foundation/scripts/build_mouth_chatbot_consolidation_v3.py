#!/usr/bin/env python3
"""Build v3 consolidation: explicit-Viv identity plus architecture/tool/memory replay."""
from __future__ import annotations
import hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; TREE=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"; ROOT=TREE/"mouth_training_chatbot_consolidation_v3"; IDREF=TREE/"mouth_training_identity_refinement_v1"/"train_32.jsonl"; ARCH=TREE/"mouth_training_arch_tool_repair_v1"/"train_48.jsonl"; ANCHOR=TREE/"mouth_training_recovery_v2_anchor_coverage_v1_3"/"train_256.jsonl"; PARENT=FOUNDATION/"models/Training/runs/mouth_training_chatbot_consolidation_v2/adapter_step_96"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def main():
    if ROOT.exists(): raise FileExistsError(f"refuse_overwrite:{ROOT}")
    identity=read(IDREF); arch=read(ARCH); memory=[x for x in read(ANCHOR) if x.get("axis")=="memory_ownership_and_service_attribution"][:16]
    if len(identity)!=32 or len(arch)!=48 or len(memory)!=16: raise ValueError("source_count_mismatch")
    rows=[]
    for label,source in (("identity_refinement",identity),("arch_tool_replay",arch),("memory_replay",memory)):
        for i,row in enumerate(source):
            x=dict(row); x.update(pair_id=f"chatbot-consolidation-v3-{label}-{i:03d}",candidate_id=f"chatbot-consolidation-v3-{label}-{i:03d}",split="train",optimizer_eligible=True,hold_only=False,response_only_loss_allowed=True,training_authorized=False,run_authorized=False,consolidation_source=label); rows.append(x)
    if len(rows)!=96 or len({x["ask_hash"] for x in rows})!=96: raise ValueError("overlap_failure")
    ROOT.mkdir(parents=True); tp=ROOT/"train_96.jsonl"; tp.write_text("".join(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8",newline="\n")
    manifest={"schema_version":"mouth_chatbot_consolidation_manifest_v3","experiment_id":"mouth_training_chatbot_consolidation_v3","created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"CORPUS_READY_TRAINING_CLOSED","training_authorized":False,"run_authorized":False,"optimizer_rows":96,"learning_rate":2e-5,"parent_adapter":{"path":str(PARENT).replace("\\","/"),"sha256":sha(PARENT/"adapter_model.safetensors")},"source_counts":{"identity_refinement":32,"arch_tool_replay":48,"memory_replay":16},"train_96_sha256":sha(tp),"evaluation_contract":{"development_count":64,"blind_count":32,"source_campaign":str(TREE/"mouth_training_recovery_v2_anchor_coverage_v1_3").replace("\\","/")},"automatic_retry":False}
    (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n"); (ROOT/"CORPUS_REPORT.md").write_text("# Viv Chatbot Consolidation v3\n\n96 rows: explicit-Viv identity refinement (32), architecture/tool replay (48), and memory replay (16). Parent is v2 step 96. LR is 2e-5. Evaluation remains the unchanged full 96-case gate.\n",encoding="utf-8",newline="\n"); print(json.dumps({"output":str(ROOT),"train":96,"train_sha256":sha(tp),"run_authorized":False,"training_authorized":False},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
