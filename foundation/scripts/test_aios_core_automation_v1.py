"""Selftest for unified AIOS core automation + sibling bundle integration."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_core_automation import (  # noqa: E402
    COLD_START_PHASES,
    RECEIPTS_ROOT,
    ROADMAP_REFS,
    get_profile,
    inventory_rows,
    list_profiles,
    phase_map,
    run_bundle_plan_only,
    run_plan,
    write_receipt,
)


def main() -> int:
    assert "cold_start" in ROADMAP_REFS and ROADMAP_REFS["cold_start"].endswith("COLD_START.md")
    assert set(COLD_START_PHASES) == set(range(9))

    profiles = list_profiles()
    assert profiles, "no profiles registered"
    ids = {row["profile_id"] for row in profiles}
    assert "backup_uml_lane" in ids
    assert "infra" in ids
    assert "carma" in ids
    assert all("cold_start_phase" in row for row in profiles)

    # Profiles must be non-decreasing by COLD_START phase.
    phases = [int(row["cold_start_phase"]) for row in profiles]
    assert phases == sorted(phases), phases

    backup = get_profile("backup_uml_lane")
    assert backup is not None and backup.cold_start_phase == 2
    carma = get_profile("carma")
    assert carma is not None and carma.execute_allowed is False and carma.cold_start_phase == 2

    for profile_id in ("infra", "privacy", "fractal", "data", "carma", "utils", "main", "dream"):
        result = run_plan(profile_id)
        assert result.get("aios_runtime_started") is False, (profile_id, result)
        assert result.get("gpu_long_launched") is False, (profile_id, result)
        assert result.get("ok") is True, (profile_id, result)

    backup_plan = run_plan("backup_uml_lane")
    assert backup_plan.get("ok") is True, backup_plan
    assert backup_plan.get("mode") == "plan_only", backup_plan

    # Integrated plan-only bundle (preflight + training catalog + backup plan).
    bundle = run_bundle_plan_only(preflight_profile="quick")
    assert bundle.get("aios_runtime_started") is False, bundle
    assert bundle.get("gpu_long_launched") is False, bundle
    assert bundle.get("mode") == "plan_only", bundle
    siblings = bundle.get("siblings") or {}
    assert "systems_preflight" in siblings and "training_catalog" in siblings and "backup_uml_lane" in siblings
    assert siblings["systems_preflight"].get("ok") is True, siblings["systems_preflight"]
    assert siblings["training_catalog"].get("ok") is True, siblings["training_catalog"]
    assert siblings["training_catalog"].get("gpu_long_launched") is False
    assert int(siblings["training_catalog"].get("job_count") or 0) >= 1
    assert siblings["backup_uml_lane"].get("ok") is True, siblings["backup_uml_lane"]
    assert siblings["backup_uml_lane"].get("mode") == "plan_only"
    # Preflight exposes plan_only_ready filter + backup automation_entry.
    assert int(siblings["systems_preflight"].get("plan_only_ready_count") or 0) >= 1
    assert any(
        row.get("automation_entry") for row in (siblings["systems_preflight"].get("automation_entries") or [])
    ), siblings["systems_preflight"]
    assert bundle.get("ok") is True, bundle

    receipt = write_receipt(bundle, stamp="selftest_aios_core_automation_bundle")
    assert receipt.is_file(), receipt
    latest = RECEIPTS_ROOT / "LATEST.json"
    assert latest.is_file(), latest

    rows = inventory_rows()
    assert any(row.get("profile") == "backup_uml_lane" and row.get("cold_start_phase") == 2 for row in rows)
    assert any(row.get("core") == "federation" and row.get("execute_allowed") is False for row in rows)

    pm = phase_map()
    assert "bundle" in pm and "plan_only" in pm["bundle"]
    assert 0 in pm["bundle"]["plan_only"]["cold_start_phases"]

    report = {
        "ok": True,
        "profile_count": len(profiles),
        "inventory_rows": len(rows),
        "bundle_receipt": str(receipt).replace("\\", "/"),
        "preflight_receipt": siblings["systems_preflight"].get("receipt"),
        "backup_receipt": siblings["backup_uml_lane"].get("backup_receipt"),
        "training_job_count": siblings["training_catalog"].get("job_count"),
        "aios_runtime_started": False,
        "gpu_long_launched": False,
        "deny_weight_packs": True,
        "cold_start_phases_covered_by_bundle": pm["bundle"]["plan_only"]["cold_start_phases"],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
