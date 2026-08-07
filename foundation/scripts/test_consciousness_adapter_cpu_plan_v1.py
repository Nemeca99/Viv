"""Regression for the read-only consciousness adapter cpu_plan surface."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_consciousness import cpu_plan  # noqa: E402


def main() -> int:
    plan = cpu_plan(
        prompt="truthful system documentation",
        experience={
            "nodes": {"truth": {"weight": 1.0}, "evidence": {"weight": 1.0}},
            "edges": [("evidence", "CAUSES", "truth"), ("evidence", "MECHANISM", "truth")],
        },
        explicit_commit=False,
    )
    assert plan["ok"] is True, plan
    assert plan["writes_performed"] is False, plan
    assert plan["durable_commit_performed"] is False, plan
    assert plan["llm_authority"] is False, plan
    assert plan["aios_runtime_started"] is False, plan
    assert plan["viv_executes_v2"] is False, plan
    assert plan["fragment"]["selected"] == "oracle", plan
    assert plan["identity_drift"]["drift"] is False, plan
    assert plan["cycle"]["memory_commit"]["state"] == "NOT_DUE", plan
    assert plan["commit_handoff"]["executor_handoff"] == "HOLD", plan

    handoff = cpu_plan(prompt="truthful system documentation", explicit_commit=True)
    assert handoff["durable_commit_performed"] is False, handoff
    assert handoff["commit_handoff"]["executor_handoff"] == "READY_FOR_GOVERNED_EXECUTOR", handoff
    assert handoff["writes_performed"] is False, handoff

    print(
        json.dumps(
            {
                "ok": True,
                "fragment": plan["fragment"]["selected"],
                "commit_state": plan["cycle"]["memory_commit"]["state"],
                "handoff_with_intent": handoff["commit_handoff"]["executor_handoff"],
                "writes_performed": False,
                "durable_commit_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
