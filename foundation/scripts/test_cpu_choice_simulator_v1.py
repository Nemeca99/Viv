"""Regression for deterministic three-action CPU choice simulation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_choice_simulator import simulate_choices  # noqa: E402
from lib.agentic_runtime import Task, _execute  # noqa: E402


def main() -> int:
    good = simulate_choices(["restore", "action", "idle"], ["restore", "action", "idle"])
    assert good["ok"] and good["accuracy"] == 1.0 and good["loop_penalty_total"] == 0.0
    loop = simulate_choices(["action"] * 6, ["idle"] * 6)
    assert loop["ok"] and loop["loop_penalty_total"] > 0.0 and any(row["loop_detected"] for row in loop["rows"])
    bounded = simulate_choices(["idle"] * 400, ["idle"] * 400, max_steps=10)
    assert bounded["steps"] == 10 and bounded["bounded"] is True and bounded["master_s_n_changed"] is False
    task_ok, task_result = _execute(Task(task_id="test-cpu-choice", title="choice simulation", kind="cpu_choice_simulation", payload={"oracle_actions": ["restore", "action"], "choices": ["restore", "action"]}), 0.5)
    assert task_ok is True and "VERIFIED_SIMULATION" in task_result
    print(json.dumps({"ok": True, "correct_accuracy": good["accuracy"], "loop_penalty": loop["loop_penalty_total"], "bounded_steps": bounded["steps"], "task_ok": task_ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
