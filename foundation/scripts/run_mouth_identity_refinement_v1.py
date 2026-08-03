#!/usr/bin/env python3
"""Governed low-LR explicit-Viv identity refinement runner."""
from __future__ import annotations
import argparse,gc,hashlib,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
FOUNDATION=Path(__file__).resolve().parents[1]; REPO=FOUNDATION.parent
for p in (FOUNDATION,REPO,Path(__file__).resolve().parent):
    if str(p) not in sys.path: sys.path.insert(0,str(p))
from models.Training.code import train_mouth_v3_targeted_patch as trainer  # noqa: E402
from models.Training.code import train_stage1_mouth_generation_canary as canary  # noqa: E402
ROOT=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_identity_refinement_v1"; TRAIN=ROOT/"train_32.jsonl"; PARENT=FOUNDATION/"models/Training/runs/mouth_training_chatbot_consolidation_v2/adapter_step_96"; ID="mouth_training_identity_refinement_v1"; PROMPT="You are Viv's GPU mouth inside AIOS. Speak naturally from verified CPU-supplied context. Do not claim human identity or independent tool agency."; OPTIMIZER_ROWS=32; OPTIMIZER_STEPS=32; LEARNING_RATE=5e-6; CHECKPOINT_STEPS=(8,16,24,32); ANCHOR_STRENGTH=0.0
def utc(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    if p.exists(): raise FileExistsError(f"refuse_overwrite:{p}")
    p.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); return sha(p)
def install():
    plan={"schema_version":"mouth_identity_refinement_plan_v1","experiment_id":ID,"created_utc":utc(),"status":"RUNNER_INSTALLED_RUN_UNAUTHORIZED","implementation_authorized":True,"run_authorized":False,"training_authorized":False,"promotion_authorized":False,"deployment_authorized":False,"optimizer_rows":OPTIMIZER_ROWS,"optimizer_steps":OPTIMIZER_STEPS,"learning_rate":LEARNING_RATE,"gradient_accumulation":4,"warmup_ratio":0.05,"seed":42,"precision":"bf16","response_only_loss":True,"parent_adapter":str(PARENT).replace("\\","/"),"pre_run_locks":{"train_jsonl":{"path":str(TRAIN).replace("\\","/"),"sha256":sha(TRAIN)},"parent_adapter":{"path":str(PARENT).replace("\\","/"),"sha256":sha(PARENT/"adapter_model.safetensors")},"trainer_source":{"path":str(Path(trainer.__file__)).replace("\\","/"),"sha256":sha(Path(trainer.__file__))}},"checkpoint_steps":list(CHECKPOINT_STEPS),"output_root":str(FOUNDATION/"models/Training/runs"/ID).replace("\\","/"),"automatic_retry":False}
    ps=write(ROOT/"campaign_plan.json",plan); write(ROOT/"STATUS.json",{"experiment_id":ID,"status":plan["status"],"implementation_authorized":True,"run_authorized":False,"training_authorized":False,"campaign_plan_sha256":ps}); return {"plan_sha256":ps,"run_authorized":False,"training_authorized":False}
def preflight():
    import torch
    plan=json.loads((ROOT/"campaign_plan.json").read_text(encoding="utf-8"));
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(): raise RuntimeError("cuda_bf16_required:identity_refinement_preflight")
    layout=trainer.dry_lease_path_layout(run_id=f"exact_nostep_{ID}",sandbox_parent=REPO/"sandbox/exact_runtime_preflight"); prepared=None
    try:
            prepared=trainer.prepare_targeted_patch_runtime(train_jsonl=TRAIN,parent_adapter=PARENT,system_prompt=PROMPT,learning_rate=LEARNING_RATE,gradient_accumulation=4,staging_root=layout["staging_root"],final_root=layout["final_root"],load_model=True,expected_rows=OPTIMIZER_ROWS,max_steps=OPTIMIZER_STEPS,warmup_ratio=0.05,anchor_strength=ANCHOR_STRENGTH); report={"schema_version":"mouth_identity_refinement_nostep_v1","experiment_id":ID,"recorded_utc":utc(),"pass":True,"optimizer_rows":len(prepared["encoded"]),"optimizer_steps_configured":OPTIMIZER_STEPS,"optimizer_steps_executed":0,"forward_executed":False,"backward_executed":False,"optimizer_step_executed":False,"lease_begin_run_called":False,"lora_coverage":prepared["coverage"],"anchor_strength":ANCHOR_STRENGTH,"run_authorized":False,"training_authorized":False}
    finally:
        if prepared is not None:
            for k in ("optimizer","model","tokenizer"):
                if prepared.get(k) is not None: del prepared[k]
        gc.collect(); torch.cuda.empty_cache()
    write(ROOT/"EXACT_RUNTIME_NOSTEP_PREFLIGHT.json",report); return report
def authorize():
    pp=ROOT/"campaign_plan.json"; plan=json.loads(pp.read_text(encoding="utf-8")); pf=json.loads((ROOT/"EXACT_RUNTIME_NOSTEP_PREFLIGHT.json").read_text(encoding="utf-8"));
    if pf.get("pass") is not True or pf.get("optimizer_steps_executed")!=0: raise ValueError("preflight_not_pass")
    token_path=canary.named_authorization_path(ID)
    if token_path.exists(): raise FileExistsError(f"token_exists:{token_path}")
    now=utc(); a=dict(plan); a.update(run_authorized=True,training_authorized=False,status="RUN_AUTHORIZED_AWAITING_CONSUME",authorized_at=now); stage=ROOT/"campaign_plan.authorize_stage"; stage.write_text(json.dumps(a,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); ps=sha(stage); token={"schema_version":canary.NAMED_UNLOCK_SCHEMA_VERSION,"experiment_id":ID,"plan_sha256":ps,"status":"issued","issued_at":now,"issued_by":"identity_refinement_authorize_once"}; ts=token_path.with_suffix(".authorize_stage"); token_path.parent.mkdir(parents=True,exist_ok=True); ts.write_text(json.dumps(token,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); os.replace(str(stage),str(pp)); os.replace(str(ts),str(token_path)); (ROOT/"STATUS.json").write_text(json.dumps({"experiment_id":ID,"status":a["status"],"implementation_authorized":True,"run_authorized":True,"training_authorized":False,"campaign_plan_sha256":sha(pp)},indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); return {"plan_sha256":sha(pp),"run_authorized":True,"training_authorized":False}
def run():
    pp=ROOT/"campaign_plan.json"; plan=json.loads(pp.read_text(encoding="utf-8"));
    if plan.get("run_authorized") is not True: raise ValueError("run_not_authorized")
    token=canary.consume_named_hard_stop_authorization(experiment_id=ID,plan_sha256=sha(pp)); result={"schema_version":"mouth_identity_refinement_result_v1","experiment_id":ID,"started_utc":utc(),"token":token,"token_consumed":True,"ok":False}
    try:
        result["training"]=trainer.train_targeted_patch_16_single_lease(train_jsonl=TRAIN,parent_adapter=PARENT,system_prompt=PROMPT,run_id=ID,learning_rate=LEARNING_RATE,max_steps=OPTIMIZER_STEPS,checkpoint_steps=CHECKPOINT_STEPS,expected_rows=OPTIMIZER_ROWS,warmup_ratio=0.05,anchor_strength=ANCHOR_STRENGTH); result["ok"]=bool(result["training"].get("ok")); result["finished_utc"]=utc(); return result
    finally:
        plan=json.loads(pp.read_text(encoding="utf-8")); plan.update(run_authorized=False,training_authorized=False,status="REARMED_RUN_UNAUTHORIZED",rearmed_at=utc()); pp.write_text(json.dumps(plan,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); (ROOT/"STATUS.json").write_text(json.dumps({"experiment_id":ID,"status":plan["status"],"implementation_authorized":True,"run_authorized":False,"training_authorized":False,"campaign_plan_sha256":sha(pp)},indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n"); write(ROOT/"FINAL_RUN_RESULT.json",result)
if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("mode",choices=("install-preflight","preflight","authorize","run")); a=parser.parse_args()
    if a.mode=="install-preflight": print(json.dumps({"install":install(),"preflight":preflight()},indent=2,sort_keys=True,default=str))
    elif a.mode=="preflight": print(json.dumps(preflight(),indent=2,sort_keys=True,default=str))
    elif a.mode=="authorize": print(json.dumps(authorize(),indent=2,sort_keys=True,default=str))
    else: print(json.dumps(run(),indent=2,sort_keys=True,default=str))
