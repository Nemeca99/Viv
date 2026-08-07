#!/usr/bin/env python3
"""Selftest for RID / plant foundation automation (plan-first, no 120s stress)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.rid_plant_automation_v1 import (  # noqa: E402
    HEALTH_QUICK_BUDGET_S,
    LONG_PLANT_COMMAND,
    LONG_PLANT_SECONDS,
    PROFILE_HEALTH_QUICK,
    RECEIPTS_ROOT,
    SCHEMA_RECEIPT,
    build_plan_receipt,
    list_profiles,
    long_plant_gate,
    plan_health_quick,
    run_health_quick,
    write_receipt,
)


def main() -> int:
    errors: list[str] = []

    profiles = list_profiles()
    if not profiles:
        errors.append("no profiles")
    ids = {p["profile_id"] for p in profiles}
    if PROFILE_HEALTH_QUICK not in ids:
        errors.append("missing health_quick profile")

    # Plan-only must never approve long plant auto-run.
    plan = plan_health_quick(i_understand_long_plant=False)
    if plan.get("execution_approved") is not False:
        errors.append("plan execution_approved should be False")
    if plan.get("aios_runtime_started") is not False:
        errors.append("plan aios_runtime_started must be False")
    if plan.get("include_stress") is not False:
        errors.append("plan must keep stress off")
    long0 = plan.get("long_plant") or {}
    if long0.get("status") != "SKIP":
        errors.append(f"long plant without gate should SKIP, got {long0.get('status')}")
    if long0.get("auto_execute") is not False:
        errors.append("long plant auto_execute must be False")
    if long0.get("command") is not None:
        errors.append("long plant command must be absent without gate")

    gated = long_plant_gate(i_understand_long_plant=True)
    if gated.get("status") != "DOCUMENTED":
        errors.append(f"gated long plant should be DOCUMENTED, got {gated.get('status')}")
    if gated.get("auto_execute") is not False:
        errors.append("even with gate, auto_execute must stay False")
    if gated.get("command") != list(LONG_PLANT_COMMAND):
        errors.append("documented command mismatch")
    if LONG_PLANT_SECONDS != 120:
        errors.append("LONG_PLANT_SECONDS must be 120")
    if "--stress" not in LONG_PLANT_COMMAND:
        errors.append("documented command must include --stress")

    receipt = build_plan_receipt(i_understand_long_plant=False, stamp="selftest_rid_plant_plan")
    if receipt.get("schema_version") != SCHEMA_RECEIPT:
        errors.append("schema_version mismatch")
    if receipt.get("mode") != "plan_only":
        errors.append("build_plan_receipt mode must be plan_only")
    path = write_receipt(receipt, stamp="selftest_rid_plant_plan")
    if not path.is_file():
        errors.append(f"receipt missing: {path}")
    if RECEIPTS_ROOT not in path.parents and path.parent.parent != RECEIPTS_ROOT:
        # stamp folder under RECEIPTS_ROOT
        if path.parent.parent.name != "rid_plant_automation" and path.parent.parent != RECEIPTS_ROOT:
            if RECEIPTS_ROOT not in path.resolve().parents:
                errors.append(f"receipt not under receipts root: {path}")

    # Execute path must stay under budget and never start long plant / AIOS.
    result = run_health_quick(i_understand_long_plant=False)
    if result.get("aios_runtime_started") is not False:
        errors.append("execute aios_runtime_started must be False")
    if result.get("long_plant_started") is not False:
        errors.append("execute long_plant_started must be False")
    if result.get("include_stress") is not False:
        errors.append("execute include_stress must be False")
    if float(result.get("elapsed_s") or 0) > HEALTH_QUICK_BUDGET_S + 5:
        errors.append(
            f"health_quick exceeded budget: {result.get('elapsed_s')} > {HEALTH_QUICK_BUDGET_S}"
        )
    lp = result.get("long_plant") or {}
    if lp.get("auto_execute") is not False:
        errors.append("execute path must not auto long plant")
    if lp.get("status") != "SKIP":
        errors.append("execute without gate should SKIP long plant")

    check_ids = {c.get("id") for c in (result.get("checks") or [])}
    for required in (
        "foundation_health_gate",
        "rid_adapter_status",
        "uml_plant_sn_gate",
        "rid_feed_meta",
        "plant_runtime_probe",
        "rid_pid_probe",
    ):
        if required not in check_ids:
            errors.append(f"missing check id: {required}")

    # SKIP rows must carry a reason (when present).
    for row in result.get("checks") or []:
        if row.get("status") == "SKIP" and not row.get("reason"):
            errors.append(f"SKIP without reason: {row.get('id')}")

    exec_receipt = {
        "schema_version": SCHEMA_RECEIPT,
        "stamp": "selftest_rid_plant_exec",
        **result,
    }
    exec_path = write_receipt(exec_receipt, stamp="selftest_rid_plant_exec")
    if not exec_path.is_file():
        errors.append(f"exec receipt missing: {exec_path}")

    report = {
        "ok": len(errors) == 0,
        "errors": errors,
        "profile": PROFILE_HEALTH_QUICK,
        "plan_receipt": str(path).replace("\\", "/"),
        "exec_receipt": str(exec_path).replace("\\", "/"),
        "elapsed_s": result.get("elapsed_s"),
        "budget_s": HEALTH_QUICK_BUDGET_S,
        "failed_checks": result.get("failed"),
        "skipped_count": len(result.get("skipped") or []),
        "aios_runtime_started": False,
        "long_plant_started": False,
        "long_plant_auto_execute": False,
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
