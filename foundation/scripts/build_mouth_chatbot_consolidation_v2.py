#!/usr/bin/env python3
"""Create a new execution campaign after v1's external timeout; corpus bytes are unchanged."""
from __future__ import annotations
import hashlib, json, shutil
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION=Path(__file__).resolve().parents[1]
TREE=FOUNDATION/"artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
SOURCE=TREE/"mouth_training_chatbot_consolidation_v1"; ROOT=TREE/"mouth_training_chatbot_consolidation_v2"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if ROOT.exists(): raise FileExistsError(f"refuse_overwrite:{ROOT}")
    ROOT.mkdir(parents=True); train=ROOT/"train_96.jsonl"; shutil.copy2(SOURCE/"train_96.jsonl",train)
    old=json.loads((SOURCE/"manifest.json").read_text(encoding="utf-8"))
    manifest={"schema_version":"mouth_chatbot_consolidation_manifest_v2","experiment_id":"mouth_training_chatbot_consolidation_v2","created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"CORPUS_READY_TRAINING_CLOSED","training_authorized":False,"run_authorized":False,"optimizer_rows":96,"source_campaign":str(SOURCE).replace("\\","/"),"source_manifest_sha256":sha(SOURCE/"manifest.json"),"train_96_sha256":sha(train),"parent_adapter":old["parent_adapter"],"evaluation_contract":old["evaluation_contract"],"automatic_retry":False,"reason":"v1_external_timeout_before_final_commit; new execution identity with identical corpus and parent"}
    (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")
    (ROOT/"CORPUS_REPORT.md").write_text("# Viv Chatbot Consolidation v2\n\nByte-identical corpus to v1. New execution identity exists only because v1 was externally timed out after staged training before final commit. No automatic retry; this campaign remains closed until explicit execution.\n",encoding="utf-8",newline="\n")
    print(json.dumps({"output":str(ROOT),"train_96_sha256":sha(train),"source_v1_sha256":sha(SOURCE/"train_96.jsonl"),"run_authorized":False,"training_authorized":False},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
