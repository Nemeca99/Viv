#!/usr/bin/env python3
"""Read-only parity check between the V9 rows and TRL completion masking."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import torch
from transformers import AutoTokenizer
from trl.trainer.sft_trainer import DataCollatorForLanguageModeling

from models.Training.code.train_mouth_v3_targeted_patch import OPENASTER_EOS_TOKEN, LOCAL_BASE


CAMPAIGN = ROOT / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v3_campaign_v9"
TRAIN = CAMPAIGN / "train_276.jsonl"
OUTPUT = ROOT / "artifacts/auto/agentic/trl_v9_masking_compatibility_v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    rows = [json.loads(line) for line in TRAIN.read_text(encoding="utf-8").splitlines() if line.strip()]
    tokenizer = AutoTokenizer.from_pretrained(str(LOCAL_BASE), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    eos_id = tokenizer.convert_tokens_to_ids(OPENASTER_EOS_TOKEN)
    if eos_id is None or eos_id == tokenizer.unk_token_id:
        raise ValueError("openaster_eos_missing")

    examples = []
    expected_completion_ids = []
    for row in rows:
        prompt_ids = tokenizer(str(row["ask"]), add_special_tokens=False)["input_ids"]
        target_ids = tokenizer(str(row.get("chosen") or row["target"]), add_special_tokens=False)["input_ids"] + [eos_id]
        examples.append({"input_ids": prompt_ids + target_ids, "completion_mask": [0] * len(prompt_ids) + [1] * len(target_ids)})
        expected_completion_ids.append(target_ids)

    collator = DataCollatorForLanguageModeling(tokenizer.pad_token_id, completion_only_loss=True)
    batch = collator(examples)
    failures = []
    for index, expected in enumerate(expected_completion_ids):
        labels = batch["labels"][index].tolist()
        observed = [token for token in labels if token != -100]
        if observed != expected:
            failures.append({"index": index, "pair_id": rows[index]["pair_id"], "expected_tokens": len(expected), "observed_tokens": len(observed)})

    result = {
        "schema_version": "trl_v9_masking_compatibility_v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS" if not failures else "FAIL",
        "trl_version": "0.17.0",
        "transformers_version": __import__("transformers").__version__,
        "peft_version": __import__("peft").__version__,
        "campaign_id": "mouth_training_recovery_v3_campaign_v9",
        "train_rows": len(rows),
        "train_sha256": sha256(TRAIN),
        "completion_only_loss": True,
        "rows_checked": len(rows),
        "failures": failures,
        "training_authorized": False,
        "run_authorized": False,
        "model_loaded": False,
        "gpu_steps": 0,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": result["status"] == "PASS", "status": result["status"], "rows_checked": len(rows), "failures": len(failures), "output": str(OUTPUT)}, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
