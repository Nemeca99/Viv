#!/usr/bin/env python3
"""Build the canonical 96-row chatbot-stage consolidation corpus; no training/auth."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
ROOT = TREE / "mouth_training_chatbot_consolidation_v1"
IDENTITY = TREE / "mouth_training_identity_anchor_repair_v1" / "train_32.jsonl"
ARCH_TOOL = TREE / "mouth_training_arch_tool_repair_v1" / "train_48.jsonl"
ANCHOR = TREE / "mouth_training_recovery_v2_anchor_coverage_v1_3" / "train_256.jsonl"
DEV = TREE / "mouth_training_recovery_v2_anchor_coverage_v1_3" / "development_64.jsonl"
BLIND = TREE / "mouth_training_recovery_v2_anchor_coverage_v1_3" / "blind_32.jsonl"
PARENT = FOUNDATION / "models/Training/runs/mouth_training_identity_anchor_repair_v1/adapter_step_32"

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path: Path) -> list[dict]: return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def main() -> int:
    if ROOT.exists(): raise FileExistsError(f"refuse_overwrite:{ROOT}")
    identity = read(IDENTITY); arch_tool = read(ARCH_TOOL)
    memory = [row for row in read(ANCHOR) if row.get("axis") == "memory_ownership_and_service_attribution"][:16]
    if len(identity) != 32 or len(arch_tool) != 48 or len(memory) != 16: raise ValueError("source_row_count_mismatch")
    train=[]
    for source_name, source_rows in (("identity_replay", identity), ("arch_tool_replay", arch_tool), ("memory_replay", memory)):
        for index, row in enumerate(source_rows):
            item=dict(row)
            item.update({"pair_id":f"chatbot-consolidation-{source_name}-{index:03d}","candidate_id":f"chatbot-consolidation-{source_name}-{index:03d}","split":"train","optimizer_eligible":True,"hold_only":False,"response_only_loss_allowed":True,"training_authorized":False,"run_authorized":False,"consolidation_source":source_name})
            train.append(item)
    if len(train) != 96 or len({r["pair_id"] for r in train}) != 96 or len({r["ask_hash"] for r in train}) != 96: raise ValueError("consolidation_identity_or_overlap_failure")
    ROOT.mkdir(parents=True)
    train_path=ROOT/"train_96.jsonl"; train_path.write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in train),encoding="utf-8",newline="\n")
    manifest={"schema_version":"mouth_chatbot_consolidation_manifest_v1","experiment_id":"mouth_training_chatbot_consolidation_v1","created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"status":"CORPUS_READY_TRAINING_CLOSED","training_authorized":False,"run_authorized":False,"optimizer_rows":96,"source_counts":{"identity_replay":32,"arch_tool_replay":48,"memory_replay":16},"parent_adapter":{"path":str(PARENT).replace("\\","/"),"sha256":sha(PARENT/"adapter_model.safetensors")},"sources":{"identity_replay":{"path":str(IDENTITY).replace("\\","/"),"sha256":sha(IDENTITY),"count":32},"arch_tool_replay":{"path":str(ARCH_TOOL).replace("\\","/"),"sha256":sha(ARCH_TOOL),"count":48},"memory_replay":{"path":str(ANCHOR).replace("\\","/"),"sha256":sha(ANCHOR),"selected_count":16}},"evaluation_contract":{"development":{"path":str(DEV).replace("\\","/"),"sha256":sha(DEV),"count":64},"blind":{"path":str(BLIND).replace("\\","/"),"sha256":sha(BLIND),"count":32}},"files":{"train_96.jsonl":{"path":str(train_path).replace("\\","/"),"sha256":sha(train_path),"count":96}},"no_retry_same_campaign":True}
    manifest_path=ROOT/"manifest.json"; manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")
    (ROOT/"CORPUS_REPORT.md").write_text("# Viv Chatbot Consolidation v1\n\nCanonical 96-row rehearsal campaign: 32 identity rows, 48 architecture/tool-boundary rows, and 16 memory-service rows. Parent is the committed identity-repair step 32. Evaluation remains the unchanged disjoint 64 development + 32 blind pack. Training and deployment are closed.\n",encoding="utf-8",newline="\n")
    print(json.dumps({"output":str(ROOT),"train":96,"manifest_sha256":sha(manifest_path),"training_authorized":False,"run_authorized":False},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
