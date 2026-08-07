#!/usr/bin/env python3
"""Selftest for system skeleton smoke plan catalog (no full smoke execute)."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_system_smoke_v1 import (  # noqa: E402
    RECEIPTS_ROOT,
    SCHEMA_VERSION,
    SMOKE_CATALOG,
    SMOKE_KIND,
    TARGET_WALL_S,
    aggregate_verdict,
    plan_catalog,
    StepResult,
)


def main() -> int:
    assert SMOKE_KIND == "skeleton"
    assert SCHEMA_VERSION.startswith("viv_aios_system_smoke")
    assert TARGET_WALL_S <= 300
    assert len(SMOKE_CATALOG) >= 8

    plan = plan_catalog()
    assert plan.get("ok") is True
    assert plan.get("smoke_kind") == "skeleton"
    assert plan.get("aios_runtime_started") is False
    assert plan.get("gpu_long_launched") is False
    assert "skeleton_skip_ok" in (plan.get("constraints") or [])

    step_ids = [s["step_id"] for s in plan["steps"]]
    required = {
        "systems_preflight",
        "core_automation_plan",
        "training_uml_status",
        "rid_plant_plan",
        "voice_contracts",
        "cognitive_cores",
        "service_cores",
        "backup_uml_lane_plan",
        "uml_bridge_security_gate",
        "field_scoped_bridge_canary",
        "intent_uml_request_ingress",
        "aios_subagent_list",
        "aios_subagent_selftest",
    }
    missing = required - set(step_ids)
    assert not missing, missing

    canary = next(s for s in plan["steps"] if s["step_id"] == "field_scoped_bridge_canary")
    assert "--enable-canary" in canary["args"]
    assert "--no-append-thesis" in canary["args"]

    backup = next(s for s in plan["steps"] if s["step_id"] == "backup_uml_lane_plan")
    assert "--plan-only" in backup["args"]
    assert "uml_lane" in backup["args"]

    # Aggregation: PASS + SKELETON SKIP → PASS; any FAIL → FAIL.
    pass_skip = [
        StepResult("a", "A", "PASS", 1.0, 0, "x", [], 0, None, "ok", "PLAN_ONLY"),
        StepResult(
            "b", "B", "SKIP", 0.0, 1, "y", [], None, None, "SKELETON: vacant", "PLAN_ONLY"
        ),
    ]
    assert aggregate_verdict(pass_skip) == "PASS"
    with_fail = pass_skip + [
        StepResult("c", "C", "FAIL", 1.0, 2, "z", [], 1, None, "exit 1", "CONTRACT")
    ]
    assert aggregate_verdict(with_fail) == "FAIL"
    assert aggregate_verdict([]) == "INCONCLUSIVE"

    # Prefer present scripts for core skeleton; vacant list is informational.
    present = int(plan.get("scripts_present") or 0)
    assert present >= 8, plan.get("vacant_skeleton_slots")

    print(
        "SYSTEM_SKELETON_SMOKE_SELFTEST_PASS "
        f"steps={plan['step_count']} present={present} "
        f"receipts_root={str(RECEIPTS_ROOT).replace(chr(92), '/')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
