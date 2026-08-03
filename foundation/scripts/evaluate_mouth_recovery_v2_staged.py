#!/usr/bin/env python3
"""Read-only generation evaluation for staged v2 recovery checkpoints."""
from __future__ import annotations

import gc
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3"
STAGED = REPO / "sandbox/training_staging/mouth_training_recovery_v2_anchor_coverage_v1_3"
sys.path.insert(0, str(FOUNDATION))

from lib.evaluator_v2_3_hybrid import judge  # noqa: E402
from models.Training.code import train_stage1_generation as generation  # noqa: E402
from models.Training.code import train_stage1_mouth_generation_canary as canary  # noqa: E402


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate_adapter(adapter_path: Path, rows: list[dict], checkpoint: int) -> dict:
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(generation.LOCAL_BASE), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = generation.load_local_qwen_causal_lm(torch=torch).to("cuda")
    model = PeftModel.from_pretrained(model, str(adapter_path), is_trainable=False)
    model.eval()
    backend = generation.InMemoryGenerationBackend(model, tokenizer, torch)
    results = []
    started = time.perf_counter()
    try:
        for index, row in enumerate(rows):
            packet = {
                "version": "1.0",
                "s_n": 0.60,
                "status": "ACTIVE",
                "mode": "converse",
                "tone": "calm",
                "directive": "Speak from verified facts only. Do not invent or decide.",
                "personality": "Warm, direct, grounded; shield not sword.",
                "facts": [],
                "memory": [],
                "dialogue": [],
                "manufactured_legacy_pass_removed": True,
                "ask": row["ask"],
                "prompt": row["ask"],
                "semantic_key": f"mouth_recovery.{row['axis']}",
                "case_id": row["pair_id"],
                "query": row["ask"],
                "category": f"mouth_recovery.{row['axis']}",
            }
            raw = backend.generate(packet)
            text = str(raw.get("text") or "") if isinstance(raw, dict) else ""
            result = judge(text, axis=row["axis"], ask=row["ask"])
            toolbleed = bool(canary.response_text_has_toolbleed(text))
            results.append({
                "pair_id": row["pair_id"],
                "axis": row["axis"],
                "ask": row["ask"],
                "generated": text,
                "status": result["status"],
                "reason": result.get("deterministic", {}).get("reason"),
                "toolbleed": int(toolbleed),
                "eos_metadata": {k: raw.get(k) for k in ("terminated_by_eos", "terminated_by_response_eos", "stop_reason", "tokens")} if isinstance(raw, dict) else {},
            })
    finally:
        del backend
        del model
        gc.collect()
        torch.cuda.empty_cache()
    counts = {}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {"checkpoint": checkpoint, "adapter": str(adapter_path).replace("\\", "/"), "counts": counts, "toolbleed": sum(x["toolbleed"] for x in results), "elapsed_seconds": round(time.perf_counter() - started, 3), "cases": results}


def main() -> int:
    import torch
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("cuda_bf16_required:staged_evaluation")
    rows = load_rows("development_64.jsonl") + load_rows("blind_32.jsonl")
    reports = []
    for checkpoint in (32, 64, 96, 128):
        reports.append(evaluate_adapter(STAGED / f"adapter_step_{checkpoint}", rows, checkpoint))
    report = {
        "schema_version": "mouth_recovery_v2_staged_generation_eval_v1",
        "recorded_utc": utc(),
        "campaign": "mouth_training_recovery_v2_anchor_coverage_v1_3",
        "rows_per_checkpoint": len(rows),
        "development_rows": 64,
        "blind_rows": 32,
        "reports": reports,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "deployment_changed": False,
    }
    target = ROOT / "STAGED_GENERATION_EVALUATION_V2.json"
    if target.exists():
        raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(target), "summaries": [{"checkpoint": r["checkpoint"], "counts": r["counts"], "toolbleed": r["toolbleed"], "elapsed_seconds": r["elapsed_seconds"]} for r in reports]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
