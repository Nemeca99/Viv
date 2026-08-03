#!/usr/bin/env python3
"""Write the final read-only readiness report for the entity-aware full run."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_full_run_entity_we_v1"
SOURCE = ROOT.parent / "mouth_training_recovery_v2_anchor_coverage_v1_3"
REPORT = ROOT / "RUN_READINESS_REPORT.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if REPORT.exists():
        raise FileExistsError(f"refuse_overwrite:{REPORT}")
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((ROOT / "campaign_plan.json").read_text(encoding="utf-8"))
    preflight = json.loads((ROOT / "EXACT_RUNTIME_NOSTEP_PREFLIGHT.json").read_text(encoding="utf-8"))
    train = [json.loads(line) for line in (ROOT / "train_256.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    negatives = [json.loads(line) for line in (ROOT / "ENTITY_WE_JUDGE_ONLY.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    checks = {
        "campaign_manifest_locked": manifest["status"] == "CORPUS_READY_TRAINING_CLOSED",
        "optimizer_rows_exact_256": len(train) == 256 and all(row.get("optimizer_eligible") is True for row in train),
        "axis_balance_64_each": all(sum(row.get("axis") == axis for row in train) == 64 for axis in manifest["axis_counts"]),
        "entity_positive_rows_three": sum(bool(row.get("entity_we_contract")) for row in train) == 3,
        "entity_negative_rows_judge_only": len(negatives) == 3 and all(row.get("optimizer_eligible") is False and row.get("hold_only") is True for row in negatives),
        "preflight_pass": preflight.get("pass") is True,
        "preflight_zero_steps": preflight.get("optimizer_steps_executed") == 0 and preflight.get("optimizer_step_executed") is False,
        "preflight_no_lease": preflight.get("lease_begin_run_called") is False,
        "auth_closed": plan.get("run_authorized") is False and plan.get("training_authorized") is False,
        "no_output_root": not Path(plan["checkpoint_paths"]["run_root"]).exists(),
        "source_campaign_preserved": sha(SOURCE / "manifest.json") == manifest["source_campaign"]["manifest_sha256"] and sha(SOURCE / "train_256.jsonl") == manifest["source_campaign"]["train_sha256"],
    }
    report = {
        "schema_version": "mouth_full_run_entity_we_readiness_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "GREEN_TO_AUTHORIZE_FULL_RUN" if all(checks.values()) else "NOT_READY",
        "experiment_id": plan["experiment_id"],
        "campaign_root": str(ROOT).replace("\\", "/"),
        "campaign_manifest_sha256": sha(ROOT / "manifest.json"),
        "campaign_plan_sha256": sha(ROOT / "campaign_plan.json"),
        "checks": checks,
        "preflight": {"path": str(ROOT / "EXACT_RUNTIME_NOSTEP_PREFLIGHT.json").replace("\\", "/"), "sha256": sha(ROOT / "EXACT_RUNTIME_NOSTEP_PREFLIGHT.json"), "optimizer_rows": preflight.get("optimizer_rows"), "optimizer_steps_executed": preflight.get("optimizer_steps_executed"), "lease_begin_run_called": preflight.get("lease_begin_run_called")},
        "authority": {"implementation_authorized": plan.get("implementation_authorized"), "run_authorized": plan.get("run_authorized"), "training_authorized": plan.get("training_authorized"), "promotion_authorized": plan.get("promotion_authorized"), "deployment_authorized": plan.get("deployment_authorized")},
        "next_action": "Operator may separately authorize one named run; authorization is not issued by this report.",
        "no_training_performed": True,
        "no_promotion_or_deployment": True,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    report["report_sha256"] = sha(REPORT)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
