"""Focused tests for the enterprise audit adapter CPU planner."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_audit import cpu_plan  # noqa: E402


def main() -> int:
    plan = cpu_plan(
        python_source='"""fixture"""\ndef f(value: str) -> str:\n    """fixture"""\n    return value\n',
        python_path="foundation/lib/fixture.py",
        json_config={"mode": "cpu"},
        required_keys=("mode",),
        observations=[{"path": "fixture.py", "state": "PASS", "score": 100}],
        controls=[{"id": "CC1", "state": "PASS"}],
        report_type="compliance",
        audit_action="review",
    )
    assert plan["ok"], plan
    assert plan["sections"]["compliance"]["disposition"] == "COMPLIANT", plan
    assert plan["sections"]["report"]["report_write_performed"] is False, plan
    assert plan["sections"]["audit_event"]["append_performed"] is False, plan
    assert plan["filesystem_scan_performed"] is False, plan
    assert plan["audit_write_performed"] is False, plan
    assert plan["external_integration_performed"] is False, plan
    print(
        json.dumps(
            {
                "ok": True,
                "failed_sections": plan["failed_sections"],
                "compliance": plan["sections"]["compliance"]["disposition"],
                "report_write_performed": plan["sections"]["report"]["report_write_performed"],
                "audit_write_performed": plan["audit_write_performed"],
                "external_integration_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
