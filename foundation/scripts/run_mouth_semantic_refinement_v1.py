#!/usr/bin/env python3
"""Governed 32-step parented semantic refinement; no promotion/deployment."""
from __future__ import annotations
import argparse,gc,hashlib,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
F=Path(__file__).resolve().parents[1]; REPO=F.parent
for p in (F,REPO,Path(__file__).resolve().parent):
 if str(p) not in sys.path: sys.path.insert(0,str(p))
from models.Training.code import train_mouth_v3_targeted_patch as trainer
from models.Training.code import train_stage1_mouth_generation_canary as canary
ROOT=F/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v1"; TRAIN=ROOT/"train_16.jsonl"; PARENT=F/"models/Training/runs/mouth_full_run_entity_we_v1/adapter_step_128"; ID="mouth_semantic_refinement_v1"; OUT=F/"models/Training/runs"/ID; LR=1e-5; STEPS=32; CHECK=(8,16,24,32); PROMPT="You are Viv's GPU mouth inside AIOS. Speak from verified CPU-supplied context. Do not invent, decide, claim human identity, or claim independent tool agency."
def utc(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(path,obj):
 if path.exists(): raise FileExistsError(f"refuse_overwrite:{path}")
 path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); return sha(path)
def install():
 plan={"schema_version":"mouth_semantic_refinement_plan_v1","experiment_id":ID,"created_utc":utc(),"status":"RUNNER_INSTALLED_RUN_UNAUTHORIZED","implementation_authorized":True,"run_authorized":False,"training_authorized":False,"promotion_authorized":False,"deployment_authorized":False,"optimizer_rows":16,"optimizer_steps":STEPS,"learning_rate":LR,"gradient_accumulation":4,"warmup_ratio":0.05,"seed":42,"precision":"bf16","response_only_loss":True,"parent_adapter":str(PARENT).replace("\\","/"),"checkpoint_steps":list(CHECK),"output_root":str(OUT).replace("\\","/"),"pre_run_locks":{"train_jsonl":{"path":str(TRAIN).replace("\\","/"),"sha256":sha(TRAIN)},"parent_adapter":{"path":str(PARENT).replace("\\","/"),"sha256":sha(PARENT/"adapter_model.safetensors")},"trainer_source":{"path":str(Path(trainer.__file__)).replace("\\","/"),"sha256":sha(Path(trainer.__file__))}},"automatic_retry":False}
 ps=write(ROOT/"campaign_plan.json",plan); write(ROOT/"STATUS.json",{"experiment_id":ID,"status":plan["status"],"implementation_authorized":True,"run_authorized":False,"training_authorized":False,"campaign_plan_sha256":ps}); return {"plan_sha256":ps,"run_authorized":False,"training_authorized":False}
def preflight():
 import torch
 plan=json.loads((ROOT/"campaign_plan.json").read_text()); layout=trainer.dry_lease_path_layout(run_id=f"exact_nostep_{ID}",sandbox_parent=F/"sandbox/exact_runtime_preflight"); prepared=None
 if plan["run_authorized"] or plan["training_authorized"]: raise ValueError("authorization_not_closed")
 if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(): raise RuntimeError("cuda_bf16_required:semantic_refinement_preflight")
 try:
  prepared=trainer.prepare_targeted_patch_runtime(train_jsonl=TRAIN,parent_adapter=PARENT,system_prompt=PROMPT,learning_rate=LR,gradient_accumulation=4,staging_root=layout["staging_root"],final_root=layout["final_root"],load_model=True,expected_rows=16,max_steps=STEPS,warmup_ratio=.05)
  r={"schema_version":"mouth_semantic_refinement_nostep_v1","experiment_id":ID,"recorded_utc":utc(),"pass":True,"optimizer_rows":len(prepared["encoded"]),"optimizer_steps_configured":STEPS,"optimizer_steps_executed":0,"forward_executed":False,"backward_executed":False,"optimizer_step_executed":False,"lease_begin_run_called":False,"run_authorized":False,"training_authorized":False,"lora_coverage":prepared["coverage"]}
 finally:
  if prepared:
   for k in ("optimizer","model","tokenizer"):
    if prepared.get(k) is not None: del prepared[k]
  gc.collect(); torch.cuda.empty_cache()
 write(ROOT/"EXACT_RUNTIME_NOSTEP_PREFLIGHT.json",r); return r
def authorize():
 p=ROOT/"campaign_plan.json"; plan=json.loads(p.read_text()); pf=json.loads((ROOT/"EXACT_RUNTIME_NOSTEP_PREFLIGHT.json").read_text()); token_path=canary.named_authorization_path(ID)
 if pf.get("pass") is not True or pf.get("optimizer_steps_executed")!=0 or token_path.exists() or OUT.exists(): raise ValueError("authorize_preconditions_failed")
 a=dict(plan); a.update(run_authorized=True,training_authorized=False,status="RUN_AUTHORIZED_AWAITING_CONSUME",authorized_at=utc()); staged=p.with_suffix(".authorize_stage"); staged.write_text(json.dumps(a,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); ps=sha(staged); ts=token_path.with_suffix(".authorize_stage"); token_path.parent.mkdir(parents=True,exist_ok=True); ts.write_text(json.dumps({"schema_version":canary.NAMED_UNLOCK_SCHEMA_VERSION,"experiment_id":ID,"plan_sha256":ps,"status":"issued","issued_at":utc(),"issued_by":"semantic_refinement_authorize_once"},indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); os.replace(staged,p); os.replace(ts,token_path); (ROOT/"STATUS.json").write_text(json.dumps({"experiment_id":ID,"status":a["status"],"implementation_authorized":True,"run_authorized":True,"training_authorized":False,"campaign_plan_sha256":sha(p)},indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); return {"plan_sha256":sha(p),"run_authorized":True,"training_authorized":False}
def run():
 p=ROOT/"campaign_plan.json"; plan=json.loads(p.read_text());
 if plan.get("run_authorized") is not True: raise ValueError("run_not_authorized")
 token=canary.consume_named_hard_stop_authorization(experiment_id=ID,plan_sha256=sha(p)); result={"schema_version":"mouth_semantic_refinement_result_v1","experiment_id":ID,"started_utc":utc(),"token":token,"token_consumed":True,"ok":False}
 try:
  result["training"]=trainer.train_targeted_patch_16_single_lease(train_jsonl=TRAIN,parent_adapter=PARENT,system_prompt=PROMPT,run_id=ID,learning_rate=LR,max_steps=STEPS,checkpoint_steps=CHECK,expected_rows=16,warmup_ratio=.05); result["ok"]=bool(result["training"].get("ok")); result["finished_utc"]=utc(); return result
 finally:
  a=json.loads(p.read_text()); a.update(run_authorized=False,training_authorized=False,status="REARMED_RUN_UNAUTHORIZED",rearmed_at=utc()); p.write_text(json.dumps(a,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); (ROOT/"STATUS.json").write_text(json.dumps({"experiment_id":ID,"status":a["status"],"implementation_authorized":True,"run_authorized":False,"training_authorized":False,"campaign_plan_sha256":sha(p)},indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); write(ROOT/"FINAL_RUN_RESULT.json",result)
if __name__=="__main__":
 ap=argparse.ArgumentParser(); ap.add_argument("mode",choices=("install-preflight","preflight","authorize","run")); a=ap.parse_args()
 if a.mode=="install-preflight": out={"install":install(),"preflight":preflight()}
 elif a.mode=="preflight": out=preflight()
 elif a.mode=="authorize": out=authorize()
 else: out=run()
 print(json.dumps(out,indent=2,sort_keys=True,default=str))
