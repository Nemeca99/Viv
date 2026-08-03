"""Regression for fail-closed CPU action execution."""
from __future__ import annotations

import json
import sys
from unittest.mock import patch
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_action_contract import build_contract  # noqa: E402
from lib.cpu_action_executor import execute_contract  # noqa: E402
from lib.cpu_state_snapshot import build_snapshot, capture_live  # noqa: E402
from lib.agentic_runtime import Task, _execute  # noqa: E402


def main() -> int:
    state = build_snapshot(s_n=0.8, queued_work=0, sources={"test": "fixture"})
    idle = build_contract(task_id="idle", action="idle", state=state)
    idle_result = execute_contract(idle, state)
    assert idle_result["ok"] and idle_result["state"] == "EXECUTED_NOOP" and idle_result["writes_performed"] is False
    action = build_contract(task_id="action", action="action", state=state)
    closed = execute_contract(action, state)
    assert closed["ok"] is False and closed["reason"] == "effect_binding_closed"
    restore = build_contract(task_id="restore", action="restore", state=state, allowed_effects=("dream_consolidation",), side_effects_allowed=True)
    with patch("lib.aios_dream.perform_dream_cycle", return_value={"ok": True, "cycle": 1}) as dream:
        restored = execute_contract(restore, state)
    assert restored["ok"] is True and restored["state"] == "EXECUTED" and restored["writes_performed"] is True and dream.called
    drift = execute_contract(idle, dict(state, s_n=0.2))
    assert drift["ok"] is False and drift["reason"] == "contract_verification_failed"
    live = capture_live()
    live_idle = build_contract(task_id="live-idle", action="idle", state=live)
    ok, result = _execute(Task(task_id="test-action-execute", title="noop execute", kind="cpu_action_execute", payload={"contract": live_idle}), 0.5)
    assert ok is True and "EXECUTED_NOOP" in result
    print(json.dumps({"ok": True, "idle_noop": True, "effect_closed": True, "drift_denied": True, "runtime_task_ok": ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
