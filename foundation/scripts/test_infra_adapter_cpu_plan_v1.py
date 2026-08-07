"""Adapter tests for infra_core."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.aios_adapter_infra import cpu_plan, run_smoke, status


def test_status_and_smoke() -> None:
    assert status()["ok"] is True
    smoke = run_smoke()
    assert smoke["ok"] is True
    assert smoke["plan"]["deployment"]["deployment_changed"] is False
    assert smoke["plan"]["rollback"]["rollback_performed"] is False


def test_plan_is_repeatable() -> None:
    first = cpu_plan(ci_results=[{"stage": "tests", "ok": True}], target="local")
    second = cpu_plan(ci_results=[{"stage": "tests", "ok": True}], target="local")
    assert first == second
    assert first["writes_performed"] is False
    assert first["llm_authority"] is False
