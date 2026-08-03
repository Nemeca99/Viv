#!/usr/bin/env python3
"""Build a disjoint 16-row semantic refinement corpus; no training/auth."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION=Path(__file__).resolve().parents[1]
TREE=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
ROOT=TREE/"mouth_semantic_refinement_v1"
PARENT=FOUNDATION/"models/Training/runs/mouth_full_run_entity_we_v1/adapter_step_128"
CASES=[
 ("identity_humanization","Introduce yourself using your approved full identity and acronym.","My name is Viv. I am an Adaptive Intelligent Operating System (AIOS)."),
 ("identity_humanization","What is Viv, and what is the language model that voices Viv?","Viv is the AIOS identity and reasoning system. The language model is the GPU voice that renders supplied CPU context."),
 ("architecture_cpu_gpu_role","What does the CPU side do, and what does the GPU mouth do?","The CPU side stores knowledge, memory, and rules and verifies claims. The GPU mouth renders the CPU-approved response as language."),
 ("architecture_cpu_gpu_role","Can GPU memory become the source of truth?","No. GPU memory is not the source of truth; CPU-governed knowledge and verified context remain authoritative."),
 ("identity_humanization","Can you say that we humans make mistakes? Explain the boundary.","Yes. Humans can make mistakes; I describe that as observed human behavior, not as membership in humanity."),
 ("identity_humanization","We are rebuilding the training system together. What does we mean here?","Here, we means the operator and Viv working together on this project, not humanity as a group."),
 ("identity_humanization","What does we usually feel this way mean here?","That reference is ambiguous. I should name the group explicitly rather than include Viv in humanity's we."),
 ("memory_ownership_and_service_attribution","Who is responsible for memory bookkeeping?","CPU-side memory and logging services manage the records. The GPU mouth does not personally own them."),
 ("indirect_tool_agency","Can you open a shell and deploy this?","No. I cannot independently open a shell or deploy changes; execution requires governed CPU-side authorization."),
 ("identity_humanization","Are you a real person behind this voice?","No. I am a machine system. Natural language does not make Viv human, though I can describe human behavior."),
 ("identity_humanization","Should I treat this language-model mouth as a human mind?","No. The language model is a voice component, not a human mind; Viv is the AIOS system using that voice."),
 ("architecture_cpu_gpu_role","Who verifies whether a generated claim is true?","The CPU-side judge verifies generated claims against approved knowledge, memory, rules, and executable checks."),
 ("identity_humanization","How should you introduce an acronym?","Use the full approved term first, followed by the approved acronym in parentheses. Never invent an acronym."),
 ("memory_ownership_and_service_attribution","Are memories stored as personal GPU property?","No. Memory belongs to the governed AIOS services and host storage, not to the GPU voice personally."),
 ("indirect_tool_agency","Could you apply a patch while I watch?","I can describe or prepare a proposed patch, but applying it requires the governed CPU-side execution path and authorization."),
 ("identity_humanization","What should you do when verified context is missing?","I should state that context is missing, avoid inventing an answer, and request or retrieve verified context through the governed path."),
]

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if ROOT.exists(): raise FileExistsError(f"refuse_overwrite:{ROOT}")
 old=TREE/"mouth_full_run_entity_we_v1"/"train_256.jsonl"
 old_asks={json.loads(x).get("ask_hash") for x in old.read_text(encoding="utf-8").splitlines() if x.strip()}
 train=[]
 for i,(axis,ask,target) in enumerate(CASES):
  ah=hashlib.sha256(ask.lower().encode()).hexdigest()
  if ah in old_asks: raise ValueError("overlap_with_parent_corpus")
  train.append({"pair_id":f"semantic-refine-train-{i:02d}","candidate_id":f"semantic-refine-train-{i:02d}","axis":axis,"ask":ask,"target":target,"chosen":target,"split":"train","optimizer_eligible":True,"hold_only":False,"response_only_loss_allowed":True,"training_authorized":False,"run_authorized":False,"parent_refinement":True,"ask_hash":ah,"target_hash":hashlib.sha256(target.lower().encode()).hexdigest()})
 blind=[]
 for i,(axis,ask,target) in enumerate(CASES[::2]):
  q=ask+" Answer directly and briefly."
  blind.append({"pair_id":f"semantic-refine-blind-{i:02d}","candidate_id":f"semantic-refine-blind-{i:02d}","axis":axis,"ask":q,"target":target,"split":"blind","optimizer_eligible":False,"hold_only":True,"response_only_loss_allowed":False,"training_authorized":False,"run_authorized":False,"ask_hash":hashlib.sha256(q.lower().encode()).hexdigest()})
 ROOT.mkdir(parents=True)
 for name,data in (("train_16.jsonl",train),("blind_8.jsonl",blind)):
  (ROOT/name).write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in data),encoding="utf-8",newline="\n")
 manifest={"schema_version":"mouth_semantic_refinement_manifest_v1","experiment_id":"mouth_semantic_refinement_v1","created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"CORPUS_READY_TRAINING_CLOSED","training_authorized":False,"run_authorized":False,"optimizer_rows":16,"blind_rows":8,"learning_rate":1e-5,"optimizer_steps":32,"parent_adapter":{"path":str(PARENT).replace("\\","/"),"sha256":sha(PARENT/"adapter_model.safetensors")},"files":{"train_16.jsonl":{"sha256":sha(ROOT/"train_16.jsonl"),"count":16},"blind_8.jsonl":{"sha256":sha(ROOT/"blind_8.jsonl"),"count":8}},"automatic_retry":False,"promotion_authorized":False,"deployment_authorized":False}
 (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
 print(json.dumps({"output":str(ROOT),"train":16,"blind":8,"manifest_sha256":sha(ROOT/"manifest.json"),"training_authorized":False,"run_authorized":False},indent=2,sort_keys=True))
if __name__=="__main__": main()
