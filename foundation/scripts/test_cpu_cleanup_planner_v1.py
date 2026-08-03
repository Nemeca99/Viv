"""Regression for plan-only CPU cleanup decisions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_cleanup_planner import build_plan  # noqa: E402
from lib.agentic_runtime import Task, _execute  # noqa: E402


def main() -> int:
    plan = build_plan([
        {"path": "C:/Users/test/duplicate.tmp", "duplicate": True, "canonical": False},
        {"path": "C:/Windows/system32/a.dll", "duplicate": True, "canonical": False},
        {"path": "C:/Users/test/keep.txt", "canonical": True},
    ])
    assert plan["state"] == "VERIFIED_PLAN_ONLY" and plan["review_count"] == 1 and plan["deny_count"] == 1
    assert plan["moves_performed"] is False and plan["deletes_performed"] is False and plan["backup_required_before_effect"] is True
    ok, result = _execute(Task(task_id="test-cleanup-plan", title="cleanup plan", kind="cpu_cleanup_plan", payload={"candidates": [{"path": "C:/Users/test/x.tmp", "duplicate": True}]}), 0.5)
    assert ok is True and "VERIFIED_PLAN_ONLY" in result
    print(json.dumps({"ok": True, "review_count": plan["review_count"], "deny_count": plan["deny_count"], "plan_only": True, "runtime_task_ok": ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
