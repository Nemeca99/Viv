#!/usr/bin/env python3
"""Close a consumed consolidation run after an external process timeout."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION=Path(__file__).resolve().parents[1]
ROOT=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_chatbot_consolidation_v1"
TOKEN=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/authorizations/mouth_training_chatbot_consolidation_v1.json"
STAGE=FOUNDATION.parent/"sandbox/training_staging/mouth_training_chatbot_consolidation_v1"
def utc(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    plan_path=ROOT/"campaign_plan.json"; plan=json.loads(plan_path.read_text(encoding="utf-8")); token=json.loads(TOKEN.read_text(encoding="utf-8"))
    if token.get("status")!="consumed": raise ValueError("expected_consumed_token")
    if (ROOT/"FINAL_RUN_RESULT.json").exists(): raise FileExistsError("final_result_already_exists")
    staged=[p.name for p in STAGE.glob("adapter_step_*")] if STAGE.exists() else []
    plan.update(run_authorized=False,training_authorized=False,status="ABORTED_EXTERNAL_TIMEOUT_REARMED",rearmed_at=utc(),rearm_reason="runner_process_killed_after_staged_checkpoints_before_final_commit")
    plan_path.write_text(json.dumps(plan,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    status={"experiment_id":"mouth_training_chatbot_consolidation_v1","status":plan["status"],"implementation_authorized":True,"run_authorized":False,"training_authorized":False,"campaign_plan_sha256":sha(plan_path)}
    (ROOT/"STATUS.json").write_text(json.dumps(status,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    result={"schema_version":"mouth_chatbot_consolidation_abort_v1","experiment_id":"mouth_training_chatbot_consolidation_v1","ok":False,"decision":"ABORT_PRE_COMMIT_EXTERNAL_TIMEOUT","recorded_utc":utc(),"token_consumed":True,"token_status":"consumed","lease_commit":False,"deployment_changed":False,"staging_preserved":True,"staged_checkpoints":staged,"optimizer_steps_observed":72,"optimizer_steps_configured":96,"run_authorized":False,"training_authorized":False,"note":"External command timeout killed the process before runner finally rearm/commit. Staged checkpoints are preserved as evidence and are not promoted."}
    (ROOT/"FINAL_RUN_RESULT.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"status":plan["status"],"staged_checkpoints":staged,"run_authorized":False,"lease_commit":False},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
