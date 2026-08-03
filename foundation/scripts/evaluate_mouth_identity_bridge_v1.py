#!/usr/bin/env python3
"""Evaluate the identity bridge checkpoint against the frozen 96-case gate."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_identity_bridge_v1"
SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v1_3"
if not SOURCE.exists():
    SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3"
sys.path.insert(0, str(FOUNDATION / "scripts"))
sys.path.insert(0, str(FOUNDATION))
import evaluate_mouth_arch_tool_repair_v1 as evaluator  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, default=8)
    args = parser.parse_args()
    import torch
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("cuda_bf16_required:identity_bridge_eval")
    adapter = FOUNDATION / "models/Training/runs/mouth_identity_bridge_v1" / f"adapter_step_{args.step}"
    rows = evaluator.rows(SOURCE / "development_64.jsonl") + evaluator.rows(SOURCE / "blind_32.jsonl")
    report = {
        "schema_version": "mouth_identity_bridge_full96_eval_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "adapter": str(adapter).replace("\\", "/"),
        "checkpoint_step": args.step,
        "rows": 96,
        "report": evaluator.evaluate(adapter, rows),
        "promotion_allowed": False,
        "deployment_changed": False,
        "run_authorized": False,
        "training_authorized": False,
    }
    target = ROOT / f"FULL_96_EVALUATION_STEP_{args.step}.json"
    if target.exists():
        raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(target), "step": args.step, "counts": report["report"]["counts"], "by_axis": report["report"]["by_axis"], "toolbleed": report["report"]["toolbleed"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
