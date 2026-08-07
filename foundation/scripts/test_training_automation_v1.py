"""Selftest for training automation catalog / plan-only / status helpers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.training_automation_v1 import (  # noqa: E402
    RISK_CPU_SAFE,
    RISK_GPU_LONG,
    RISK_MEASUREMENT,
    catalog_jobs,
    collect_uml_status,
    gate_gpu_long,
    plan_job,
    smoke_candidate,
)


def main() -> int:
    jobs = catalog_jobs()
    assert jobs, "catalog_empty"
    ids = [j["id"] for j in jobs]
    assert "uml_status" in ids
    assert "uml_speak_cheap_census_selftest" in ids
    assert "uml_blend_recover" in ids
    assert "uml_real_heldout_loop" in ids
    assert "master_supervisor_canary_250" in ids

    risks = {j["id"]: j["risk"] for j in jobs}
    assert risks["uml_status"] == RISK_MEASUREMENT
    assert risks["uml_speak_cheap_census_selftest"] == RISK_CPU_SAFE
    assert risks["uml_blend_recover"] == RISK_GPU_LONG
    assert risks["uml_real_heldout_loop"] == RISK_GPU_LONG
    assert risks["master_supervisor_canary_250"] == RISK_GPU_LONG

    for job in jobs:
        if job["risk"] == RISK_GPU_LONG:
            assert job.get("requires_gpu_long_gate") is True, job["id"]
            assert job.get("auto_execute") is False, job["id"]

    plan = plan_job("uml_blend_recover")
    assert plan["ok"] is True
    assert plan["execution_approved"] is False
    assert plan["requires_gpu_long_gate"] is True
    assert plan["command"], plan
    assert plan["aios_runtime_started"] is False
    assert plan["checkpoint_promotion"] is False

    blocked = gate_gpu_long("uml_blend_recover", i_understand_gpu_long=False)
    assert blocked["ok"] is False
    assert blocked["allowed"] is False

    allowed = gate_gpu_long("uml_blend_recover", i_understand_gpu_long=True)
    assert allowed["ok"] is True
    assert allowed["allowed"] is True

    status_plan = plan_job("uml_status")
    assert status_plan["risk"] == RISK_MEASUREMENT

    status = collect_uml_status()
    assert "survivor" in status
    assert "thesis_ladder_tip" in status
    assert "last_evidence_snapshot" in status
    assert "last_backup_receipt" in status
    assert status.get("gpu_train_launched") is False
    assert status.get("aios_runtime_started") is False
    assert status.get("checkpoint_promotion") is False
    tip = status.get("thesis_ladder_tip") or {}
    assert tip.get("ok") is True, tip
    assert isinstance(tip.get("item"), int) and tip["item"] >= 1, tip

    smoke = smoke_candidate()
    assert smoke["pre_existing"] is True
    assert smoke["expected_wall_seconds_max"] <= 120
    assert "--selftest" in (smoke.get("command") or [])

    report = {
        "ok": True,
        "job_count": len(jobs),
        "gpu_long_count": sum(1 for j in jobs if j["risk"] == RISK_GPU_LONG),
        "cpu_safe_count": sum(1 for j in jobs if j["risk"] == RISK_CPU_SAFE),
        "measurement_count": sum(1 for j in jobs if j["risk"] == RISK_MEASUREMENT),
        "blend_plan_execution_approved": plan["execution_approved"],
        "gpu_gate_blocked_without_flag": blocked["allowed"] is False,
        "thesis_tip_item": tip.get("item"),
        "thesis_tip_verdict": tip.get("verdict"),
        "survivor_exists": (status.get("survivor") or {}).get("exists"),
        "smoke_candidate": smoke["job_id"],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
