"""Read-only CPU adapter for the deterministic ``data_core`` boundary.

This adapter exposes planning and status only.  It does not create storage,
import or export files, delete records, run database commands, or commit a
restore.  Those effects remain separate governed operations.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.data_core import (  # noqa: E402
    DEFAULT_RETENTION_DAYS,
    build_manifest,
    make_record,
    module_status as cpu_module_status,
    plan_cleanup,
    plan_export,
    plan_import,
    recovery_plan,
    storage_stats,
)
from lib.paths import AUTO_ARTIFACTS, SANDBOX_ROOT  # noqa: E402


ADAPTER_ID = "data_core"
REGISTRY_ID = "data_core"


def status() -> dict[str, Any]:
    """Return CPU data-core capability and path observations without writes."""
    return {
        "ok": True,
        "evidence": {
            "adapter": ADAPTER_ID,
            "registry_id": REGISTRY_ID,
            "cpu_planner": cpu_module_status(),
            "artifact_root_exists": AUTO_ARTIFACTS.is_dir(),
            "sandbox_root_exists": SANDBOX_ROOT.is_dir(),
            "filesystem_scan_performed": False,
            "writes_performed": False,
            "execution_performed": False,
            "llm_authority": False,
        },
    }


def cpu_plan(
    records: list[Mapping[str, Any]],
    *,
    source: str = "cpu_input",
    now_utc: str = "2026-01-01T00:00:00Z",
    retention_days: int = DEFAULT_RETENTION_DAYS,
    auto_cleanup_enabled: bool = False,
    explicit_cleanup_commit: bool = False,
) -> dict[str, Any]:
    """Build data, import, export, statistics, cleanup, and recovery plans."""
    rows = [dict(row) for row in records if isinstance(row, Mapping)]
    manifest = build_manifest(rows)
    cleanup = plan_cleanup(
        rows,
        now_utc=now_utc,
        retention_days=retention_days,
        auto_cleanup_enabled=auto_cleanup_enabled,
        explicit_commit=explicit_cleanup_commit,
    )
    return {
        "ok": bool(manifest.get("ok")) and bool(cleanup.get("ok")),
        "manifest": manifest,
        "stats": storage_stats(rows),
        "import_plan": plan_import(rows, source=source),
        "export_plan": plan_export(rows, target_format="json"),
        "cleanup_plan": cleanup,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
    }


def run_smoke() -> dict[str, Any]:
    """Exercise deterministic plans with fixed records; no evidence is written."""
    old = make_record(
        {"kind": "old", "value": "retain provenance"},
        record_id="data-smoke-old",
        record_type="fragment",
        source="smoke",
        provenance="fixture",
        created_utc="2020-01-01T00:00:00Z",
    )
    recent = make_record(
        {"kind": "recent", "value": "retain provenance"},
        record_id="data-smoke-recent",
        record_type="conversation",
        source="smoke",
        provenance="fixture",
        created_utc="2025-12-31T00:00:00Z",
    )
    rows = [old, recent]
    manifest = build_manifest(rows)
    cleanup = plan_cleanup(rows, now_utc="2026-01-01T00:00:00Z", retention_days=365)
    exact = recovery_plan(manifest["manifest"], rows)
    changed_recent = make_record(
        {"kind": "recent", "value": "changed"},
        record_id="data-smoke-recent",
        record_type="conversation",
        source="smoke",
        provenance="fixture",
        created_utc="2025-12-31T00:00:00Z",
    )
    drift = recovery_plan(manifest["manifest"], [old, changed_recent])
    ok = (
        manifest["state"] == "VERIFIED"
        and cleanup["state"] == "HOLD"
        and cleanup["delete_performed"] is False
        and exact["state"] == "VERIFIED"
        and drift["state"] == "DRIFT"
        and drift["restore_performed"] is False
    )
    return {
        "ok": ok,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "smoke",
            "manifest_state": manifest["state"],
            "cleanup_state": cleanup["state"],
            "exact_recovery_state": exact["state"],
            "drift_recovery_state": drift["state"],
            "delete_performed": cleanup["delete_performed"],
            "restore_performed": drift["restore_performed"],
            "writes_performed": False,
            "execution_performed": False,
            "llm_authority": False,
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_smoke(), indent=2, default=str))
