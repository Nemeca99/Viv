"""CPU adapter dispatcher and autonomous task integration regression."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_core_dispatch import adapter_for, available_cores, probe, probe_many  # noqa: E402
from lib.agentic_runtime import Task, _execute  # noqa: E402


def main() -> int:
    assert len(available_cores()) >= 15
    assert adapter_for("consciousness_core") == "lib.aios_adapter_consciousness"
    denied = probe("unknown_core")
    assert denied["state"] == "INCONCLUSIVE"
    bad_op = probe("rid_core", operation="write")
    assert bad_op["state"] == "DENIED"
    status = probe("consciousness_core")
    assert status["state"] == "PASS", json.dumps(status, indent=2, default=str)
    assert status["adapter_output_is_authority"] is False
    survey = probe_many(["consciousness_core", "luna_core", "support_core"])
    assert survey["count"] == 3 and survey["adapter_output_is_authority"] is False
    task = Task(task_id="test-cpu-probe", title="probe", kind="cpu_core_probe", payload={"core_id": "consciousness_core"})
    ok, result = _execute(task, 0.5)
    assert ok is True and "PASS" in result
    survey_task = Task(task_id="test-cpu-survey", title="survey", kind="cpu_core_survey", payload={})
    survey_ok, survey_result = _execute(survey_task, 0.5)
    assert survey_ok is True and "counts" in survey_result
    print(json.dumps({"ok": True, "adapter_count": len(available_cores()), "consciousness_probe": status["state"], "task_ok": ok, "survey_ok": survey_ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
