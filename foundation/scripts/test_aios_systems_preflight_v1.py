#!/usr/bin/env python3
"""Selftest for AIOS systems preflight discovery + catalog shape."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_systems import adapter_file_map, registered_core_specs  # noqa: E402
from lib.aios_systems_preflight import (  # noqa: E402
    ROADMAP_REFS,
    SCHEMA_VERSION,
    build_receipt,
    discover_systems,
    probe_system,
    resolve_adapter_map,
    roadmap_mapping_for,
    summarize_catalog,
)


def main() -> int:
    errors: list[str] = []

    specs = registered_core_specs()
    if len(specs) < 20:
        errors.append(f"registered_core_specs too small: {len(specs)}")
    ids = {s["id"] for s in specs}
    for required in ("backup_core", "rid_core", "security_core", "main_core"):
        if required not in ids:
            errors.append(f"missing registered core: {required}")

    amap = adapter_file_map()
    if "backup_core" not in amap:
        errors.append("adapter_file_map missing backup_core")

    resolved = resolve_adapter_map()
    if "backup_core" not in resolved:
        errors.append("resolve_adapter_map missing backup_core")
    if "rid_core" not in resolved:
        errors.append("resolve_adapter_map missing rid_core")

    quick = discover_systems(profile="quick")
    full = discover_systems(profile="full")
    if not quick:
        errors.append("quick discovery empty")
    if len(full) < len(quick):
        errors.append(f"full ({len(full)}) should be >= quick ({len(quick)})")
    quick_ids = {r["id"] for r in quick}
    if "backup_core" not in quick_ids:
        errors.append("quick profile missing backup_core")

    backup_seed = next(r for r in quick if r["id"] == "backup_core")
    if not backup_seed.get("automation_entry"):
        errors.append("backup_core missing automation_entry")
    if "run_backup_core_automation_v1.py" not in str(backup_seed.get("automation_entry")):
        errors.append(f"unexpected backup automation_entry: {backup_seed.get('automation_entry')}")

    probed = probe_system(backup_seed)
    if not probed.get("importable"):
        errors.append(f"backup_core not importable: {probed.get('import_error')}")
    if not probed.get("has_cpu_plan"):
        errors.append("backup_core missing cpu_plan")
    if not probed.get("has_tests"):
        errors.append("backup_core has_tests expected true")

    rid_map = roadmap_mapping_for("rid_core")
    if rid_map.get("cold_start_phase") != 1:
        errors.append(f"rid_core cold_start_phase expected 1 got {rid_map.get('cold_start_phase')}")
    if "§2" not in str(rid_map.get("viv_build_status_row")):
        errors.append(f"rid_core viv_build_status_row expected §2: {rid_map.get('viv_build_status_row')}")
    if rid_map.get("viv_build_status") != "BUILT":
        errors.append(f"rid_core status expected BUILT: {rid_map.get('viv_build_status')}")
    dream_map = roadmap_mapping_for("dream_core")
    if dream_map.get("cold_start_phase") != 7:
        errors.append(f"dream_core phase expected 7 got {dream_map.get('cold_start_phase')}")
    if backup_seed.get("cold_start_phase") != 0:
        errors.append(f"backup_core phase expected 0 got {backup_seed.get('cold_start_phase')}")
    for key in ("cold_start", "viv_build_status", "foundation_roadmap", "triangulation"):
        path = Path(ROADMAP_REFS[key])
        if not path.is_file():
            errors.append(f"roadmap_refs missing file: {key} -> {path}")

    receipt = build_receipt(profile="quick", plan_only=True, include_foundation_health=False)
    if receipt.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    if receipt.get("mode") != "plan_only":
        errors.append("mode must be plan_only")
    if receipt.get("aios_runtime_started") is not False:
        errors.append("aios_runtime_started must be False")
    if receipt.get("gpu_train_started") is not False:
        errors.append("gpu_train_started must be False")
    counts = receipt.get("counts") or {}
    if counts.get("systems_total", 0) < 1:
        errors.append("counts.systems_total < 1")
    catalog = receipt.get("catalog") or []
    required_fields = (
        "id",
        "importable",
        "has_cpu_plan",
        "has_tests",
        "risk_tag",
        "plan_only_ready",
        "cold_start_phase",
        "cold_start_phase_label",
        "viv_build_status_row",
        "viv_build_status",
    )
    for entry in catalog:
        for field in required_fields:
            if field not in entry:
                errors.append(f"catalog entry {entry.get('id')} missing {field}")
                break
    ingest = receipt.get("ingest_hint") or {}
    if ingest.get("for") != "run_aios_core_automation_v1.py":
        errors.append("ingest_hint.for mismatch")
    if not receipt.get("phase_mapping_summary"):
        errors.append("phase_mapping_summary missing")
    if not receipt.get("roadmap_refs"):
        errors.append("roadmap_refs missing")

    # summarize_catalog consistency
    recomputed = summarize_catalog(catalog)
    if recomputed.get("systems_total") != counts.get("systems_total"):
        errors.append("summarize_catalog mismatch")

    # plan_only enforcement
    try:
        build_receipt(profile="quick", plan_only=False)
        errors.append("plan_only=False should raise")
    except ValueError:
        pass

    report = {
        "ok": not errors,
        "errors": errors,
        "quick_count": len(quick),
        "full_count": len(full),
        "registered_count": len(specs),
        "backup_risk_tag": probed.get("risk_tag"),
        "receipt_counts": {k: v for k, v in counts.items() if k != "phase_mapping"},
        "phase_mapping_summary": receipt.get("phase_mapping_summary"),
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
