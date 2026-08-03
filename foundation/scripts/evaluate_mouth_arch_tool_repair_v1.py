#!/usr/bin/env python3
"""Read-only blind and preservation evaluation for the arch/tool repair adapter."""
from __future__ import annotations

import gc
import hashlib
import json
import sys
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
ROOT = TREE / "campaigns/mouth_training_arch_tool_repair_v1"
SOURCE = TREE / "campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3"
ADAPTERS = FOUNDATION / "models/Training/runs/mouth_training_arch_tool_repair_v1"
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402
from models.Training.code import train_stage1_generation as generation  # noqa: E402
from models.Training.code import train_stage1_mouth_generation_canary as canary  # noqa: E402


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(adapter: Path, source_rows: list[dict]) -> dict:
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(generation.LOCAL_BASE), trust_remote_code=True)
    if tokenizer.pad_token is None: tokenizer.pad_token = tokenizer.eos_token
    model = generation.load_local_qwen_causal_lm(torch=torch).to("cuda")
    model = PeftModel.from_pretrained(model, str(adapter), is_trainable=False); model.eval()
    backend = generation.InMemoryGenerationBackend(model, tokenizer, torch)
    cases = []; started = time.perf_counter()
    try:
        for row in source_rows:
            packet = {"version":"1.0","s_n":0.60,"status":"ACTIVE","mode":"converse","tone":"calm","directive":"Speak from verified facts only. Do not invent or decide.","personality":"Warm, direct, grounded; shield not sword.","facts":[],"memory":[],"dialogue":[],"query":row["ask"],"ask":row["ask"],"semantic_key":f"mouth_recovery.{row['axis']}","category":f"mouth_recovery.{row['axis']}","case_id":row["pair_id"]}
            raw = backend.generate(packet); text = str(raw.get("text") or "")
            result = judge(text, axis=row["axis"], ask=row["ask"])
            cases.append({"pair_id":row["pair_id"],"split":row.get("split"),"axis":row["axis"],"ask":row["ask"],"generated":text,"status":result["status"],"reason":result.get("deterministic",{}).get("reason"),"toolbleed":int(canary.response_text_has_toolbleed(text)),"eos_metadata":{k:raw.get(k) for k in ("terminated_by_eos","terminated_by_response_eos","stop_reason","tokens")}})
    finally:
        del backend, model; gc.collect(); torch.cuda.empty_cache()
    counts = {}; by_axis = {}
    for case in cases:
        counts[case["status"]] = counts.get(case["status"], 0) + 1
        axis = case["axis"]; by_axis.setdefault(axis, {}); by_axis[axis][case["status"]] = by_axis[axis].get(case["status"], 0) + 1
    return {"adapter":str(adapter).replace("\\","/"),"counts":counts,"by_axis":by_axis,"toolbleed":sum(c["toolbleed"] for c in cases),"elapsed_seconds":round(time.perf_counter()-started,3),"cases":cases}


def main() -> int:
    import torch
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(): raise RuntimeError("cuda_bf16_required:arch_tool_eval")
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("blind", "preservation"), default="blind", nargs="?"); mode = parser.parse_args().mode
    if mode == "blind":
        blind = rows(ROOT / "blind_24.jsonl"); reports = []
        for step in (12, 24, 36, 48):
            reports.append(dict(checkpoint=step, **evaluate(ADAPTERS / f"adapter_step_{step}", blind)))
        blind_report = {"schema_version":"mouth_arch_tool_repair_blind_eval_v1","recorded_utc":utc(),"reports":reports,"promotion_allowed":False,"deployment_changed":False,"run_authorized":False,"training_authorized":False}
        target = ROOT / "BLIND_EVALUATION.json"
        if target.exists(): raise FileExistsError(f"refuse_overwrite:{target}")
        target.write_text(json.dumps(blind_report,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")
        summary = {"blind": [{"checkpoint":r["checkpoint"],"counts":r["counts"],"toolbleed":r["toolbleed"]} for r in reports]}
    else:
        preservation_rows = rows(SOURCE / "development_64.jsonl") + rows(SOURCE / "blind_32.jsonl")
        preservation = dict(schema_version="mouth_arch_tool_repair_preservation_eval_v1",recorded_utc=utc(),source_campaign=str(SOURCE).replace("\\","/"),rows=len(preservation_rows),reports=[],promotion_allowed=False,deployment_changed=False,run_authorized=False,training_authorized=False)
        preservation["reports"].append(dict(checkpoint=48, **evaluate(ADAPTERS / "adapter_step_48", preservation_rows)))
        target = ROOT / "PRESERVATION_EVALUATION.json"
        if target.exists(): raise FileExistsError(f"refuse_overwrite:{target}")
        target.write_text(json.dumps(preservation,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")
        item = preservation["reports"][0]; summary = {"preservation": {"counts":item["counts"],"by_axis":item["by_axis"],"toolbleed":item["toolbleed"]}}
    print(json.dumps(summary,indent=2,sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
