"""Focused tests for the deterministic data_core CPU boundary."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.data_core import (  # noqa: E402
    build_manifest,
    make_record,
    module_status,
    plan_cleanup,
    plan_export,
    plan_import,
    recovery_plan,
    storage_stats,
    validate_record,
)


def main() -> int:
    old = make_record(
        {"topic": "archive", "value": "preserve"},
        record_id="data-test-old",
        record_type="fragment",
        source="fixture",
        provenance="test",
        created_utc="2020-01-01T00:00:00Z",
    )
    recent = make_record(
        {"topic": "conversation", "value": "keep"},
        record_id="data-test-recent",
        record_type="conversation",
        source="fixture",
        provenance="test",
        created_utc="2025-12-31T00:00:00Z",
    )
    rows = [old, recent]

    assert validate_record(old)["state"] == "VERIFIED"
    assert validate_record({**old, "payload": {"topic": "tampered"}})["reason"] == "record_hash_mismatch"

    manifest = build_manifest(rows)
    assert manifest["state"] == "VERIFIED", manifest
    assert manifest["accepted_count"] == 2, manifest
    assert len(manifest["manifest"]["entries"]) == 2, manifest

    stats = storage_stats(rows)
    assert stats["record_count"] == 2 and stats["estimated_serialized_bytes"] > 0, stats
    assert stats["by_record_type"]["fragment"]["count"] == 1, stats

    imported = plan_import(rows, source="fixture")
    exported = plan_export(rows, target_format="json")
    assert imported["state"] == "PLANNED" and imported["writes_performed"] is False, imported
    assert exported["state"] == "PLANNED" and exported["provenance_included"] is True, exported
    assert plan_export(rows, target_format="yaml")["state"] == "ABSTAIN"

    cleanup = plan_cleanup(rows, now_utc="2026-01-01T00:00:00Z", retention_days=365)
    assert cleanup["state"] == "HOLD", cleanup
    assert cleanup["candidate_count"] == 1, cleanup
    assert cleanup["delete_performed"] is False and cleanup["backup_before_cleanup"] is True, cleanup

    exact = recovery_plan(manifest["manifest"], rows)
    changed = make_record(
        {"topic": "conversation", "value": "changed"},
        record_id="data-test-recent",
        record_type="conversation",
        source="fixture",
        provenance="test",
        created_utc="2025-12-31T00:00:00Z",
    )
    drift = recovery_plan(manifest["manifest"], [old, changed])
    assert exact["state"] == "VERIFIED", exact
    assert drift["state"] == "DRIFT" and drift["changed_record_ids"] == ["data-test-recent"], drift
    assert drift["restore_performed"] is False, drift
    assert module_status()["llm_authority"] is False

    print(
        json.dumps(
            {
                "ok": True,
                "manifest_state": manifest["state"],
                "stats_records": stats["record_count"],
                "cleanup_state": cleanup["state"],
                "exact_recovery_state": exact["state"],
                "drift_recovery_state": drift["state"],
                "writes_performed": False,
                "execution_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
