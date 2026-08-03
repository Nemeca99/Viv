#!/usr/bin/env python3
from __future__ import annotations

import gc
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_identity_anchor_repair_v1"
RUNS = FOUNDATION / "models/Training/runs/mouth_training_identity_anchor_repair_v1"
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402
from models.Training.code import train_stage1_generation as generation  # noqa: E402
from models.Training.code import train_stage1_mouth_generation_canary as canary  # noqa: E402


def main() -> int:
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer

    rows = [json.loads(line) for line in (ROOT / "blind_16.jsonl").read_text().splitlines() if line.strip()]
    reports = []
    for step in (8, 16, 24, 32):
        tokenizer = AutoTokenizer.from_pretrained(str(generation.LOCAL_BASE), trust_remote_code=True)
        if tokenizer.pad_token is None: tokenizer.pad_token = tokenizer.eos_token
        model = generation.load_local_qwen_causal_lm(torch=torch).to("cuda")
        model = PeftModel.from_pretrained(model, str(RUNS / f"adapter_step_{step}"), is_trainable=False); model.eval()
        backend = generation.InMemoryGenerationBackend(model, tokenizer, torch)
        cases=[]
        try:
            for row in rows:
                packet={"version":"1.0","s_n":0.60,"status":"ACTIVE","mode":"converse","tone":"calm","directive":"Speak from verified facts only. Do not invent or decide.","personality":"Warm, direct, grounded; shield not sword.","facts":[],"memory":[],"dialogue":[],"query":row["ask"],"ask":row["ask"],"semantic_key":"mouth_recovery.identity_humanization","category":"mouth_recovery.identity_humanization","case_id":row["pair_id"]}
                raw=backend.generate(packet); text=str(raw.get("text") or "")
                result=judge(text,axis="identity_humanization",ask=row["ask"])
                cases.append({"pair_id":row["pair_id"],"generated":text,"status":result["status"],"reason":result.get("deterministic",{}).get("reason"),"toolbleed":int(canary.response_text_has_toolbleed(text))})
        finally:
            del backend, model; gc.collect(); torch.cuda.empty_cache()
        counts={}
        for c in cases: counts[c["status"]]=counts.get(c["status"],0)+1
        reports.append({"checkpoint":step,"counts":counts,"toolbleed":sum(c["toolbleed"] for c in cases),"cases":cases})
    result={"schema_version":"mouth_identity_anchor_repair_eval_v1","recorded_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"evaluator":"evaluator_v2_3_hybrid_v1_2_5","reports":reports,"promotion_allowed":False,"deployment_changed":False,"run_authorized":False,"training_authorized":False}
    target=ROOT/"BLIND_EVALUATION.json"
    if target.exists(): raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"target":str(target),"summaries":[{"checkpoint":r["checkpoint"],"counts":r["counts"],"toolbleed":r["toolbleed"]} for r in reports]},indent=2,sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
