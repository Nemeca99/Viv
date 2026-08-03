#!/usr/bin/env python3
"""Record the evidence-based stopping point for this training phase."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
F=Path(__file__).resolve().parents[1]
ROOT=F/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_full_run_entity_we_v1"
REF=F/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v1"
OUT=REF/"DIMINISHING_RETURNS_REPORT.json"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists(): raise FileExistsError(f"refuse_overwrite:{OUT}")
 base=json.loads((ROOT/"REAL_TEST_CHAT_STEP128.json").read_text())
 refine=json.loads((REF/"REAL_TEST_CHAT_SEMANTIC32.json").read_text())
 full=json.loads((ROOT/"CHECKPOINT_GENERATION_EVALUATION.json").read_text())
 train=json.loads((REF/"FINAL_RUN_RESULT.json").read_text())
 report={
  "schema_version":"mouth_training_diminishing_returns_report_v1",
  "recorded_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
  "status":"BEHAVIORAL_REFINEMENT_PLATEAU_HOLD",
  "selected_base_checkpoint":"mouth_full_run_entity_we_v1/adapter_step_128",
  "refinement_checkpoint":"mouth_semantic_refinement_v1/adapter_step_32",
  "full_run_curve":[{"step":r["checkpoint_step"],"pass":r["pass"],"hold":r["hold"],"fail":r["fail"],"toolbleed":r["toolbleed"]} for r in full["reports"]],
  "refinement_fit":{"steps":train["training"]["optimizer_steps"],"nll_initial":train["training"]["initial_teacher_forced"]["mean_response_nll"],"nll_final":train["training"]["final_teacher_forced"]["mean_response_nll"],"token_accuracy_initial":train["training"]["initial_teacher_forced"]["token_accuracy"],"token_accuracy_final":train["training"]["final_teacher_forced"]["token_accuracy"]},
  "chat_artifacts":{"base":{"path":str(ROOT/"REAL_TEST_CHAT_STEP128.json").replace("\\","/"),"sha256":sha(ROOT/"REAL_TEST_CHAT_STEP128.json")},"refinement":{"path":str(REF/"REAL_TEST_CHAT_SEMANTIC32.json").replace("\\","/"),"sha256":sha(REF/"REAL_TEST_CHAT_SEMANTIC32.json")}},
  "observed_remaining_gaps":["canonical identity introduction still not reliably emitted","human observation versus humanity membership remains confused","project-we and system-we remain confused in natural dialogue","acronym expansion contract remains unreliable"],
  "improvements_observed":["EOS termination remained clean","independent file/code action refusal improved","uncertainty handling improved","CPU/GPU distinction became shorter and clearer"],
  "authority":{"training_authorized":False,"run_authorized":False,"promotion_authorized":False,"deployment_changed":False},
  "next_action":"Hold promotion. Repair the evaluator/corpus around the four remaining semantic gaps before another GPU run.",
 }
 OUT.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")
 print(json.dumps(report,indent=2,sort_keys=True))
if __name__=="__main__": main()
