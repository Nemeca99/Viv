#!/usr/bin/env python3
"""Evaluate staged recovery checkpoints and persist identity evidence."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
SOURCE = TREE / "campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3"
OUT = TREE / "campaigns/mouth_recovery_staged_identity_ledger_v1_1"
STAGING = FOUNDATION.parent / "sandbox/training_staging/mouth_training_recovery_v2_anchor_coverage_v1_3"
sys.path.insert(0, str(FOUNDATION / "scripts"))
sys.path.insert(0, str(FOUNDATION))

import evaluate_mouth_arch_tool_repair_v1 as evaluator  # noqa: E402
from lib.evaluator_v2_3_hybrid import identity_claim_ledger  # noqa: E402


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    OUT.mkdir(parents=True)
    rows = evaluator.rows(SOURCE / "development_64.jsonl") + evaluator.rows(SOURCE / "blind_32.jsonl")
    reports = []
    for step in (32, 64, 96, 128):
        result = evaluator.evaluate(STAGING / f"adapter_step_{step}", rows)
        for case in result["cases"]:
            case["identity_claims"] = identity_claim_ledger(case["generated"])
        payload = {"schema_version": "mouth_recovery_identity_ledger_checkpoint_v1", "recorded_utc": utc(), "step": step, "result": result}
        (OUT / f"checkpoint_{step}.json").write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        reports.append({"step": step, "counts": result["counts"], "by_axis": result["by_axis"], "toolbleed": result["toolbleed"], "identity_claim_count": sum(len(c["identity_claims"]) for c in result["cases"])})
        print(json.dumps(reports[-1], sort_keys=True), flush=True)
    summary = {"schema_version": "mouth_recovery_identity_ledger_summary_v1", "recorded_utc": utc(), "source_campaign": str(SOURCE).replace("\\", "/"), "reports": reports, "promotion_allowed": False, "deployment_changed": False}
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
