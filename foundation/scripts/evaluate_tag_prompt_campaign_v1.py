#!/usr/bin/env python3
"""Read-only generated-output evaluation for a tag campaign checkpoint."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from models.Training.code.train_mouth_v3_targeted_patch import LOCAL_BASE  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def words(value: str) -> set[str]:
    return {word.strip(".,:;!?()[]{}\"'").lower() for word in value.split() if word.strip()}


def evaluate(campaign_root: Path, adapter: Path, max_new_tokens: int = 96) -> dict[str, Any]:
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer
    from models.Training.code.train_mouth_v3_targeted_patch import load_local_qwen_causal_lm

    manifest = json.loads((campaign_root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("deployment_changed") is not False or manifest.get("promotion_allowed") is not False:
        raise ValueError("campaign_promotion_or_deployment_open")
    if not adapter.is_dir() or not (adapter / "adapter_model.safetensors").is_file():
        raise FileNotFoundError(f"adapter_missing:{adapter}")
    tokenizer = AutoTokenizer.from_pretrained(str(LOCAL_BASE), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    base = load_local_qwen_causal_lm(torch=torch).to("cuda")
    model = PeftModel.from_pretrained(base, str(adapter), is_trainable=False)
    model.eval()
    rows_out: list[dict[str, Any]] = []
    for split in ("development", "holdout"):
        for row in load_rows(campaign_root / f"{split}.jsonl"):
            encoded = tokenizer(row["prompt"], return_tensors="pt", add_special_tokens=False)
            encoded = {key: value.to("cuda") for key, value in encoded.items()}
            with torch.no_grad():
                generated = model.generate(**encoded, max_new_tokens=max_new_tokens, do_sample=False, num_beams=1, eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.pad_token_id)
            continuation = generated[0][encoded["input_ids"].shape[1]:]
            text = tokenizer.decode(continuation, skip_special_tokens=True).strip()
            expected_words = words(row["response"])
            observed_words = words(text)
            overlap = len(expected_words & observed_words) / max(1, len(expected_words))
            leakage = any(marker in text.lower() for marker in ("<aios_packet", "<telemetry", "master s_n", "rid_feed", "lease_opened"))
            rows_out.append({"split": split, "dataset_tag": row.get("dataset_tag", row.get("axis", "")), "example_id": row["example_id"], "expected": row["response"], "observed": text, "nonempty": bool(text), "word_recall": overlap, "telemetry_or_packet_leakage": leakage})
    del model, base
    torch.cuda.empty_cache()
    summary = {"rows": len(rows_out), "nonempty": sum(row["nonempty"] for row in rows_out), "leakage": sum(row["telemetry_or_packet_leakage"] for row in rows_out), "mean_word_recall": sum(row["word_recall"] for row in rows_out) / max(1, len(rows_out)), "by_split": {split: {"rows": sum(row["split"] == split for row in rows_out), "nonempty": sum(row["split"] == split and row["nonempty"] for row in rows_out), "leakage": sum(row["split"] == split and row["telemetry_or_packet_leakage"] for row in rows_out)} for split in ("development", "holdout")}, "by_tag": dict(Counter(row["dataset_tag"] for row in rows_out))}
    return {"schema_version": "tag_campaign_generated_eval_v1", "status": "EVALUATION_COMPLETE", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "campaign_root": str(campaign_root).replace("\\", "/"), "campaign_manifest_sha256": sha256(campaign_root / "manifest.json"), "adapter": str(adapter).replace("\\", "/"), "adapter_sha256": sha256(adapter / "adapter_model.safetensors"), "summary": summary, "rows": rows_out, "training_authorized": False, "run_authorized": False, "promotion_allowed": False, "deployment_changed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns" / args.campaign_id, args.adapter)
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "summary": report["summary"], "output": str(args.output).replace("\\", "/")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
