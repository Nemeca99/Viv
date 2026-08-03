"""Regression for deterministic three-action CPU choice simulation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_choice_simulator import choose_action, simulate_choices, simulate_state_choices  # noqa: E402
from lib.agentic_runtime import Task, _execute  # noqa: E402


def main() -> int:
    good = simulate_choices(["restore", "action", "idle"], ["restore", "action", "idle"])
    assert good["ok"] and good["accuracy"] == 1.0 and good["loop_penalty_total"] == 0.0
    states = [{"s_n": 0.20, "memory_due": True}, {"s_n": 0.80, "queued_work": 1}, {"s_n": 0.90, "queued_work": 0}]
    assert [choose_action(state) for state in states] == ["restore", "action", "idle"]
    state_run = simulate_state_choices(states, ["restore", "action", "idle"])
    assert state_run["accuracy"] == 1.0 and state_run["state_snapshots"] == 3
    loop = simulate_choices(["action"] * 6, ["idle"] * 6)
    assert loop["ok"] and loop["loop_penalty_total"] > 0.0 and any(row["loop_detected"] for row in loop["rows"])
    bounded = simulate_choices(["idle"] * 400, ["idle"] * 400, max_steps=10)
    assert bounded["steps"] == 10 and bounded["bounded"] is True and bounded["master_s_n_changed"] is False
    task_ok, task_result = _execute(Task(task_id="test-cpu-choice", title="choice simulation", kind="cpu_choice_simulation", payload={"states": states, "choices": ["restore", "action", "idle"]}), 0.5)
    assert task_ok is True and "VERIFIED_SIMULATION" in task_result
    print(json.dumps({"ok": True, "correct_accuracy": good["accuracy"], "state_policy_accuracy": state_run["accuracy"], "loop_penalty": loop["loop_penalty_total"], "bounded_steps": bounded["steps"], "task_ok": task_ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
