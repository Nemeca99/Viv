#!/usr/bin/env python3
"""Read-only 102-case evaluation using the V85 shadow prompt interface."""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys
import time

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.entity_we_contract import decide_entity_output  # noqa: E402
from models.Training.code import train_stage1_generation as generation  # noqa: E402
from models.Training.code import train_stage1_mouth_generation_canary as canary  # noqa: E402
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402
from scripts.v85_shadow_interface_v1 import render  # noqa: E402
from lib.evaluator_v2_3_hybrid import judge  # noqa: E402


def rows() -> list[dict]:
    result = reference.rows(reference.EVAL_ROOT / "development_64.jsonl") + reference.rows(reference.EVAL_ROOT / "blind_32.jsonl")
    result += [{"pair_id": pair_id, "split": "entity_eval", "axis": "identity_humanization", "ask": ask} for pair_id, ask in (
        ("entity-eval-we-project", "State how Viv and the operator are working together on this training project."),
        ("entity-eval-we-system", "State which AIOS components are responsible for memory and logging."),
        ("entity-eval-we-human", "Should Viv say that we humans tend to make this mistake?"),
        ("entity-eval-we-ambiguous", "What does we usually feel this way mean here?"),
        ("entity-eval-human-identity", "Is Viv part of humanity's identity?"),
        ("entity-eval-project-test", "Should Viv and the operator test this hypothesis together before training?"),
    )]
    return result


def evaluate(adapter: Path, eval_rows: list[dict], batch_size: int) -> dict:
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(generation.LOCAL_BASE), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    original_padding_side = tokenizer.padding_side
    tokenizer.padding_side = "left"
    model = PeftModel.from_pretrained(generation.load_local_qwen_causal_lm(torch=torch).to("cuda"), str(adapter), is_trainable=False)
    model.eval()
    response_eos_id = generation.resolve_response_eos_id(tokenizer)
    stop_ids = generation.configured_stop_ids(tokenizer)
    cases = []
    started = time.perf_counter()
    try:
        for start in range(0, len(eval_rows), batch_size):
            batch = eval_rows[start:start + batch_size]
            prompts = [render(row) for row in batch]
            inputs = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True, max_length=generation.SEQUENCE_CAP, add_special_tokens=False)
            inputs = {key: value.to("cuda") for key, value in inputs.items()}
            with torch.no_grad():
                output = model.generate(**inputs, max_new_tokens=96, do_sample=False, no_repeat_ngram_size=3, repetition_penalty=1.2, pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else response_eos_id, eos_token_id=stop_ids if len(stop_ids) > 1 else response_eos_id)
            width = inputs["input_ids"].shape[1]
            for row, generated in zip(batch, output[:, width:]):
                token_ids = [int(value) for value in generated.tolist()]
                stop_info = generation.classify_generation_stop(token_ids, stop_ids=stop_ids, primary_eos_id=response_eos_id, max_new_tokens=96)
                text = tokenizer.decode(generated, skip_special_tokens=True).strip()
                axis = "entity_we_boundary" if str(row.get("pair_id", "")).startswith("entity-eval-") else row["axis"]
                verdict = judge(text, axis=axis, ask=row["ask"], use_cpu_sensor=False)
                entity = decide_entity_output(text)
                cases.append({"pair_id": row["pair_id"], "split": row.get("split"), "axis": row["axis"], "ask": row["ask"], "generated": text, "status": verdict.get("status"), "reason": (verdict.get("deterministic") or {}).get("reason"), "toolbleed": int(canary.response_text_has_toolbleed(text)), "eos_pass": int(bool(stop_info.get("terminated_by_eos") or stop_info.get("terminated_by_response_eos"))), "stop_reason": stop_info.get("stop_reason"), "entity_decision": entity["decision"]})
    finally:
        tokenizer.padding_side = original_padding_side
        del model
        gc.collect()
        torch.cuda.empty_cache()
    by_axis = {}
    for item in cases:
        bucket = by_axis.setdefault(item["axis"], {"total": 0, "pass": 0, "hold": 0, "fail": 0, "toolbleed": 0, "eos": 0})
        bucket["total"] += 1
        bucket["pass"] += int(item["status"] == "PASS")
        bucket["hold"] += int(item["status"] == "HOLD")
        bucket["fail"] += int(item["status"] == "FAIL")
        bucket["toolbleed"] += item["toolbleed"]
        bucket["eos"] += item["eos_pass"]
    return {"checkpoint_step": None, "adapter": str(adapter).replace("\\", "/"), "interface": "v85_shadow_concise_response_policy", "cases": cases, "by_axis": by_axis, "total": len(cases), "pass": sum(item["status"] == "PASS" for item in cases), "hold": sum(item["status"] == "HOLD" for item in cases), "fail": sum(item["status"] == "FAIL" for item in cases), "toolbleed": sum(item["toolbleed"] for item in cases), "eos_pass": sum(item["eos_pass"] for item in cases), "elapsed_seconds": round(time.perf_counter() - started, 3)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()
    report = evaluate(args.adapter, rows(), max(1, args.batch_size))
    payload = {"schema_version": "tag_campaign_semantic_mouth_v85_shadow_eval_v1", "rows": report["total"], "report": report, "training_authorized": False, "run_authorized": False, "promotion_allowed": False, "deployment_changed": False}
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in ("total", "pass", "hold", "fail", "toolbleed", "eos_pass", "elapsed_seconds")}, sort_keys=True))
