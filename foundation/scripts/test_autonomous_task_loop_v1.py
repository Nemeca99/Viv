"""Verify CPU task selection, completion recording, and denial containment."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

VIV = Path(__file__).resolve().parents[2]
FOUNDATION = VIV / "foundation"
for path in (VIV, FOUNDATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.agentic_runtime import Task, run_once  # noqa: E402


def _state() -> dict[str, object]:
    return {"ticks": 0, "mode": "normal", "requires_operator_resume": False}


def main() -> int:
    selected = [
        Task(task_id="low", title="low", kind="noop", priority=50, created_at="2"),
        Task(task_id="high", title="high", kind="noop", priority=1, created_at="1"),
    ]
    with patch("lib.agentic_runtime.require_membrane", return_value=None), patch(
        "lib.agentic_runtime._current_s_n", return_value=0.8
    ), patch("lib.agentic_runtime.load_state", side_effect=_state), patch(
        "lib.agentic_runtime._write_state"
    ), patch("lib.agentic_runtime.append_event"), patch(
        "lib.agentic_runtime.load_queue", return_value=selected
    ), patch("lib.agentic_runtime.save_queue"):
        report = run_once(max_tasks=1)
    assert report["processed"][0]["task_id"] == "high", report
    assert report["processed"][0]["status"] == "done", report
    assert selected[1].status == "done" and selected[0].status == "ready", selected

    denied = [Task(task_id="denied", title="denied", kind="noop", priority=1)]
    with patch("lib.agentic_runtime.require_membrane", return_value=None), patch(
        "lib.agentic_runtime._current_s_n", return_value=0.8
    ), patch("lib.agentic_runtime.load_state", side_effect=_state), patch(
        "lib.agentic_runtime._write_state"
    ), patch("lib.agentic_runtime.append_event"), patch(
        "lib.agentic_runtime.load_queue", return_value=denied
    ), patch("lib.agentic_runtime.save_queue"), patch(
        "lib.agentic_runtime._execute", return_value=(False, "security_ingress_denied")
    ):
        blocked = run_once(max_tasks=1)
    assert blocked["processed"][0]["status"] == "blocked", blocked
    assert denied[0].retries == 1, denied
    print("AUTONOMOUS_TASK_LOOP_PASS priority_selection=true denial_blocks=true result_recorded=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
