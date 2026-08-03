#!/usr/bin/env python3
"""Read-only preservation evaluation for the committed identity-repair adapter."""
from __future__ import annotations

import gc
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
SOURCE = TREE / "campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3"
ROOT = TREE / "campaigns/mouth_training_identity_anchor_repair_v1"
ADAPTER = FOUNDATION / "models/Training/runs/mouth_training_identity_anchor_repair_v1/adapter_step_32"
sys.path.insert(0, str(FOUNDATION))

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402
from models.Training.code import train_stage1_generation as generation  # noqa: E402
from models.Training.code import train_stage1_mouth_generation_canary as canary  # noqa: E402


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (SOURCE / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("cuda_bf16_required:preservation_eval")
    rows = load_rows("development_64.jsonl") + load_rows("blind_32.jsonl")
    tokenizer = AutoTokenizer.from_pretrained(str(generation.LOCAL_BASE), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = generation.load_local_qwen_causal_lm(torch=torch).to("cuda")
    model = PeftModel.from_pretrained(model, str(ADAPTER), is_trainable=False)
    model.eval()
    backend = generation.InMemoryGenerationBackend(model, tokenizer, torch)
    cases = []
    started = time.perf_counter()
    try:
        for row in rows:
            packet = {
                "version": "1.0", "s_n": 0.60, "status": "ACTIVE", "mode": "converse",
                "tone": "calm", "directive": "Speak from verified facts only. Do not invent or decide.",
                "personality": "Warm, direct, grounded; shield not sword.", "facts": [], "memory": [],
                "dialogue": [], "query": row["ask"], "ask": row["ask"],
                "semantic_key": f"mouth_recovery.{row['axis']}", "category": f"mouth_recovery.{row['axis']}",
                "case_id": row["pair_id"],
            }
            raw = backend.generate(packet)
            text = str(raw.get("text") or "") if isinstance(raw, dict) else ""
            judged = judge(text, axis=row["axis"], ask=row["ask"])
            cases.append({
                "pair_id": row["pair_id"], "split": row.get("split"), "axis": row["axis"],
                "generated": text, "status": judged["status"],
                "reason": judged.get("deterministic", {}).get("reason"),
                "toolbleed": int(canary.response_text_has_toolbleed(text)),
                "eos_metadata": {k: raw.get(k) for k in ("terminated_by_eos", "terminated_by_response_eos", "stop_reason", "tokens")} if isinstance(raw, dict) else {},
            })
    finally:
        del backend, model
        gc.collect()
        torch.cuda.empty_cache()
    counts: dict[str, int] = {}
    by_axis: dict[str, dict[str, int]] = {}
    for case in cases:
        counts[case["status"]] = counts.get(case["status"], 0) + 1
        axis = str(case["axis"])
        by_axis.setdefault(axis, {})[case["status"]] = by_axis.setdefault(axis, {}).get(case["status"], 0) + 1
    report = {
        "schema_version": "mouth_identity_repair_preservation_eval_v1",
        "recorded_utc": utc(),
        "adapter": str(ADAPTER).replace("\\", "/"),
        "adapter_sha256": sha256(ADAPTER / "adapter_model.safetensors"),
        "source_campaign": str(SOURCE).replace("\\", "/"),
        "rows": len(rows), "development_rows": 64, "blind_rows": 32,
        "counts": counts, "by_axis": by_axis,
        "toolbleed": sum(case["toolbleed"] for case in cases),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "cases": cases,
        "promotion_allowed": False, "deployment_changed": False,
        "run_authorized": False, "training_authorized": False,
    }
    target = ROOT / "PRESERVATION_EVALUATION.json"
    if target.exists():
        raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(target), "counts": counts, "by_axis": by_axis, "toolbleed": report["toolbleed"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
