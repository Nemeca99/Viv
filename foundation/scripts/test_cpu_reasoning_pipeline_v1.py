"""CPU reasoning pipeline regression with verified manual retrieval and abstention."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_reasoning_pipeline import compact, reason  # noqa: E402
from lib.agentic_runtime import Task, _execute  # noqa: E402


def main() -> int:
    verified = reason("What soul fragments does the AIOS manual define?", manual_only=True, s_n=0.6)
    assert verified["ok"] is True, json.dumps(verified, indent=2, default=str)
    assert verified["state"] == "VERIFIED", compact(verified)
    packet = verified["renderer_packet"]
    assert packet and packet["telemetry_allowed"] is False
    assert packet["llm_authority"] is False
    assert verified["writes_performed"] is False

    abstain = reason("Tell me an unsupported fact about a nonexistent device", manual_only=True, s_n=0.6)
    assert abstain["ok"] is True and abstain["state"] == "ABSTAIN", compact(abstain)

    local = reason("Anarchism", local_wikipedia=True, manual_only=False, s_n=0.6, top_k=1)
    assert local["ok"] is True and local["state"] == "VERIFIED", compact(local)
    assert local["retrieval"]["mode"] == "wikipedia_local_read_only"
    assert local["renderer_packet"]["source_packet"]["three_way"]["present_sources"] == ["F_AI_DATASETS"]

    denied = reason("", s_n=0.6)
    assert denied["ok"] is False and denied["state"] == "DENIED"
    task = Task(task_id="test-cpu-reason", title="reason", kind="cpu_reasoning_probe", payload={"value": "What does the Alpha manual say about CPU mind?", "manual_only": True, "top_k": 2})
    task_ok, task_result = _execute(task, 0.6)
    assert task_ok is True and '"state": "VERIFIED"' in task_result
    print(json.dumps({"ok": True, "verified_state": verified["state"], "abstain_state": abstain["state"], "deny_state": denied["state"], "task_ok": task_ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
