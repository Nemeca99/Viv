"""Regression for live-state capture and read-only candidate ranking."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_choice_simulator import evaluate_candidates  # noqa: E402
from lib.cpu_state_snapshot import build_snapshot  # noqa: E402
from lib.agentic_runtime import Task, _execute  # noqa: E402


def main() -> int:
    snapshot = build_snapshot(s_n=0.20, queued_work=0, memory_due=True, sources={"test": "fixture"})
    ranked = evaluate_candidates(snapshot)
    assert ranked["reference_action"] == "restore"
    assert ranked["candidates"][0]["action"] == "restore"
    assert ranked["writes_performed"] is False and ranked["master_s_n_changed"] is False
    ok, result = _execute(Task(task_id="test-live-choice", title="live choice probe", kind="cpu_choice_live_probe", payload={}), 0.5)
    assert ok is True and "reference_action" in result
    print(json.dumps({"ok": True, "fixture_reference": ranked["reference_action"], "live_task_ok": ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
