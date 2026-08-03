#!/usr/bin/env python3
"""Read-only tokenizer and response-only masking audit for the hold package."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from models.Training.code import train_mouth_v3_targeted_patch as trainer
from models.Training.code.train_stage1_generation import LOCAL_BASE

from transformers import AutoTokenizer

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v3_semantic_projection_v1"
TRAIN_CANDIDATE = ROOT / "train_candidate_256_hold.jsonl"
OUT = ROOT / "TOKENIZATION_AUDIT.json"


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    rows = [json.loads(line) for line in TRAIN_CANDIDATE.read_text(encoding="utf-8").splitlines() if line.strip()]
    tokenizer = AutoTokenizer.from_pretrained(str(LOCAL_BASE), trust_remote_code=True)
    encoded = []
    failures = []
    for row in rows:
        try:
            encoded.append(trainer.tokenize_response_only(tokenizer, ask=row["ask"], target=row["chosen"], pair_id=row["pair_id"], system_prompt="unused", semantic_key=f"mouth_recovery.{row['axis']}"))
        except Exception as exc:
            failures.append({"pair_id": row.get("pair_id"), "error": f"{type(exc).__name__}:{exc}"})
    report = {
        "schema_version": "mouth_semantic_recovery_tokenization_audit_v1",
        "status": "TOKENIZATION_AND_MASKING_PASS" if not failures else "TOKENIZATION_AND_MASKING_FAIL",
        "tokenizer_path": str(LOCAL_BASE).replace("\\", "/"),
        "rows": len(rows),
        "tokenized_rows": len(encoded),
        "sequence_cap": trainer.generation_v1.SEQUENCE_CAP,
        "max_total_tokens": max((len(item["input_ids"]) for item in encoded), default=0),
        "max_prompt_tokens": max((item["prompt_tokens"] for item in encoded), default=0),
        "max_response_plus_eos": max((item["response_tokens"] for item in encoded), default=0),
        "prompt_tokens_masked": all(all(value == -100 for value in item["labels"][: item["prompt_tokens"]]) for item in encoded),
        "target_tokens_supervised": all(all(value != -100 for value in item["labels"][item["prompt_tokens"] :]) for item in encoded),
        "training_authorized": False,
        "run_authorized": False,
        "gpu_steps": 0,
        "failures": failures,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not failures, "status": report["status"], "rows": len(rows), "max_total_tokens": report["max_total_tokens"], "output": str(OUT)}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
