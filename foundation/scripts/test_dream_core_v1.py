"""Regression tests for the deterministic dream CPU boundary."""
from __future__ import annotations

import json
import sys

from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.dream_core import (  # noqa: E402
    archive_plan,
    metrics,
    module_status,
    plan_trigger,
    scan_fragments,
)


def main() -> int:
    planned = plan_trigger(
        idle_minutes=6,
        fragments_since_last=100,
        hours_since_last=24,
        pulse_bpm=0.9,
        s_n=0.8,
    )
    assert planned["state"] == "PLANNED", planned
    assert planned["mode"] == "hot_path", planned
    assert "idle_window" in planned["trigger_reasons"], planned
    assert len(planned["phases"]) == 4, planned
    assert all(row["writes_performed"] is False for row in planned["phases"]), planned

    held = plan_trigger(active_conversation=True, idle_minutes=30, s_n=0.8)
    assert held["state"] == "HOLD" and held["reason"] == "active_conversation", held
    dormant = plan_trigger(idle_minutes=30, s_n=0.2)
    assert dormant["state"] == "HOLD" and dormant["reason"] == "s_n_dormancy", dormant
    not_due = plan_trigger(idle_minutes=1, fragments_since_last=2, hours_since_last=1, s_n=0.8)
    assert not_due["state"] == "NOT_DUE", not_due

    scan = scan_fragments(
        [
            {"id": "one", "text": "The archive preserves the source.", "provenance": "test"},
            {"id": "two", "text": "The archive preserves the source.", "provenance": "test"},
            {"id": "three", "text": "", "provenance": "bad"},
        ]
    )
    assert scan["accepted_count"] == 2 and scan["rejected_count"] == 1, scan
    assert len(scan["duplicate_groups"]) == 1, scan
    archive = archive_plan(scan)
    assert archive["state"] == "PLANNED", archive
    assert archive["delete_source_records"] is False, archive
    assert archive["requires_explicit_commit"] is True, archive
    projected = metrics(scan)
    assert projected["measured_improvement"] is False, projected
    assert projected["projected_exact_dedup_records"] == 1, projected
    assert module_status()["llm_authority"] is False

    print(
        json.dumps(
            {
                "ok": True,
                "planned": planned["state"],
                "mode": planned["mode"],
                "hold": held["reason"],
                "duplicate_groups": len(scan["duplicate_groups"]),
                "archive_delete_source_records": archive["delete_source_records"],
                "measured_improvement": projected["measured_improvement"],
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

