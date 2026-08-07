"""Adapter tests for the reconciled privacy CPU boundary."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.aios_adapter_privacy import cpu_plan


def test_cpu_plan_is_non_mutating_and_repeatable() -> None:
    kwargs = {
        "config": {},
        "requested_mode": "full-auto",
        "explicit_consent": False,
        "records": [{"category": "conversation", "source_kind": "conversation"}],
        "data_action": {"action": "delete_all", "target": "all", "confirmation": "DELETE"},
    }
    first = cpu_plan(**kwargs)
    second = cpu_plan(**kwargs)
    assert first == second
    assert first["mode_change"]["state"] == "DENIED"
    assert first["data_action"]["executed"] is False
    assert first["writes_performed"] is False
    assert first["llm_authority"] is False
