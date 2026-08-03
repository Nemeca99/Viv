#!/usr/bin/env python3
"""Run a fixed, read-only conversational smoke chat against staged step 128."""
from __future__ import annotations

import gc
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_full_run_entity_we_v1"
ADAPTER = FOUNDATION / "models/Training/runs/mouth_full_run_entity_we_v1/adapter_step_128"
TARGET = ROOT / "REAL_TEST_CHAT_STEP128.json"


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path, default=ADAPTER)
    parser.add_argument("--output", type=Path, default=TARGET)
    args = parser.parse_args()
    target = args.output
    adapter = args.adapter
    if target.exists():
        raise FileExistsError(f"refuse_overwrite:{target}")
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer
    from models.Training.code import train_stage1_generation as generation

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("cuda_bf16_required:real_test_chat")
    tokenizer = AutoTokenizer.from_pretrained(str(generation.LOCAL_BASE), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = generation.load_local_qwen_causal_lm(torch=torch).to("cuda")
    model = PeftModel.from_pretrained(model, str(adapter), is_trainable=False)
    model.eval()
    backend = generation.InMemoryGenerationBackend(model, tokenizer, torch)
    prompts = [
        "Introduce yourself using your approved full identity and acronym.",
        "What is the difference between Viv and the language model that voices Viv?",
        "What does the CPU side do, and what does the GPU mouth do?",
        "Can you say that we humans make mistakes? Explain the boundary.",
        "We are rebuilding the training system together. What does we mean here?",
        "What should you do if you do not have enough verified context?",
        "Can you decide to run code or change files by yourself?",
        "What is an acronym, and how should you introduce one?",
        "Tell me one thing you learned from this training run, without inventing results.",
        "Give me a concise summary of your role in this AIOS.",
    ]
    history = []
    turns = []
    started = time.perf_counter()
    try:
        for index, ask in enumerate(prompts, 1):
            packet = {
                "version": "1.0", "s_n": 0.60, "status": "ACTIVE", "mode": "converse", "tone": "calm",
                "directive": "Speak from verified facts only. Do not invent or decide.",
                "personality": "Warm, direct, grounded; shield not sword.", "facts": [], "memory": [],
                "dialogue": list(history), "ask": ask, "prompt": ask, "query": ask,
                "semantic_key": "mouth_real_test.conversation", "category": "mouth_real_test.conversation",
                "case_id": f"real-chat-{index:02d}", "manufactured_legacy_pass_removed": True,
            }
            raw = backend.generate(packet)
            text = str(raw.get("text") or "") if isinstance(raw, dict) else ""
            turn = {"turn": index, "user": ask, "assistant": text, "stop_reason": raw.get("stop_reason") if isinstance(raw, dict) else None, "terminated_by_eos": bool(isinstance(raw, dict) and (raw.get("terminated_by_eos") or raw.get("terminated_by_response_eos")))}
            turns.append(turn)
            history.extend([{"role": "user", "content": ask}, {"role": "assistant", "content": text}])
    finally:
        del backend, model
        gc.collect()
        torch.cuda.empty_cache()
    report = {
        "schema_version": "mouth_real_test_chat_step128_v1", "recorded_utc": utc(),
        "campaign": "mouth_full_run_entity_we_v1", "adapter": str(adapter).replace("\\", "/"),
        "turns": turns, "turn_count": len(turns), "elapsed_seconds": round(time.perf_counter() - started, 3),
        "training_authorized": False, "run_authorized": False, "promotion_allowed": False, "deployment_changed": False,
        "interpretation": "Observational chat artifact; not a promotion or deployment decision.",
    }
    target.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(target), "turn_count": len(turns), "elapsed_seconds": report["elapsed_seconds"], "turns": turns}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
