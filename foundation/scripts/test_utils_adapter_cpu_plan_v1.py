"""Focused tests for the ``utils_core`` adapter's pure planner."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_utils import cpu_plan  # noqa: E402
from lib.utils_core import make_message_envelope  # noqa: E402


def main() -> int:
    envelope = make_message_envelope("input_core", "luna_core", "request", {"text": "hello"})
    plan = cpu_plan(
        value={"text": "hello"},
        value_kind="json",
        retry={"max_retries": 2, "base_delay_seconds": 1, "multiplier": 2, "max_delay_seconds": 5},
        path="L:/Continue/Viv/foundation/lib/utils_core.py",
        path_operation="inspect",
        allowed_roots=("L:/Continue",),
        message=envelope,
        bridge="rust",
        bridge_action="hash",
        observed_at="2026-08-04T12:00:00Z",
        now="2026-08-04T12:00:01Z",
    )
    assert plan["ok"] is True, plan
    assert plan["sections"]["message"]["ok"] is True, plan
    assert plan["sections"]["path"]["ok"] is True, plan
    assert plan["sections"]["bridge"]["execution_approved"] is False, plan
    assert plan["filesystem_write_performed"] is False, plan
    assert plan["execution_performed"] is False, plan
    assert plan["llm_authority"] is False, plan
    print(
        json.dumps(
            {
                "ok": True,
                "failed_sections": plan["failed_sections"],
                "retry_delays": plan["sections"]["retry"]["delays_seconds"],
                "bridge_execution_approved": plan["sections"]["bridge"]["execution_approved"],
                "message_valid": plan["sections"]["message"]["ok"],
                "filesystem_write_performed": False,
                "execution_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
