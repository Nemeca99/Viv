"""Focused tests for the manual-led Luna CPU response planner."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.luna_core import assess_rendered_response, build_response_plan  # noqa: E402


def main() -> int:
    plan = build_response_plan("Why does the security system need evidence?", grounded=True)
    assert plan["ok"] is True
    assert plan["linguistic_operator"]["operator"] == "why"
    assert plan["fragment"]["selected"] == "guardian"
    assert plan["routing"]["fact_authority"] == "retrieval_or_explicit_user_input"
    assert plan["llm_authority"] is False

    brief = build_response_plan("hello")
    assert brief["response_value"]["tier"] == "trivial"
    assert brief["response_value"]["max_tokens"] == 15

    assert assess_rendered_response("The retrieved answer is here.", grounded=True)["ok"] is True
    blocked = assess_rendered_response("My internal stability is healthy.", grounded=True)
    assert blocked["ok"] is False and blocked["telemetry_leakage"] is True
    print(json.dumps({"ok": True, "planner": plan, "containment": blocked}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
