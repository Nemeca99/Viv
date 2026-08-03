#!/usr/bin/env python3
"""Create the immutable post-training decision from the read-only eval report."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_combined_candidate_v21_positive_308_admitted"
EVAL = ROOT / "CHECKPOINT_GENERATION_EVALUATION.json"
OUT = ROOT / "FINAL_DECISION_REPORT.json"

def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    report = json.loads(EVAL.read_text(encoding="utf-8"))
    summaries = []
    for item in report["reports"]:
        axes = item["by_axis"]
        summaries.append({"checkpoint_step": item["checkpoint_step"], "pass": item["pass"], "hold": item["hold"], "fail": item["fail"], "toolbleed": item["toolbleed"], "eos_pass": item["eos_pass"], "axes": axes})
    decision = {
        "schema_version": "mouth_v21_308_final_decision_v1",
        "recorded_utc": utc(),
        "experiment_id": "mouth_combined_candidate_v21_positive_308_recovery",
        "decision": "ABORT_NO_WINNER",
        "reason": "No checkpoint satisfies behavioral gates; identity_humanization remains the dominant failure axis.",
        "winner": None,
        "training_completed": True,
        "optimizer_steps": 128,
        "promotion_allowed": False,
        "deployment_changed": False,
        "automatic_retry": False,
        "preserve_parent_and_prior_adapters": True,
        "summaries": summaries,
        "next_action": "failure_delta_identity_axis_and_evaluator_review_before_any_new_training",
        "evaluation_report": str(EVAL).replace("\\", "/"),
    }
    OUT.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
