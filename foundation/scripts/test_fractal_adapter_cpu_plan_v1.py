"""Adapter-level regression tests for fractal_core."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.aios_adapter_fractal import cpu_plan, run_smoke, status


def test_status_and_smoke() -> None:
    assert status()["ok"] is True
    smoke = run_smoke()
    assert smoke["ok"] is True
    assert smoke["plan"]["writes_performed"] is False
    assert smoke["plan"]["llm_authority"] is False


def test_plan_is_repeatable_and_effect_closed() -> None:
    kwargs = {
        "spans": [{"id": "one", "cost": 4, "value": 5}, {"id": "two", "cost": 4, "value": 4}],
        "observations": [{"score": 0.8}],
        "cache_entries": [{"hit": True}],
        "global_budget": 4,
    }
    first = cpu_plan("Build a bounded test.", **kwargs)
    second = cpu_plan("Build a bounded test.", **kwargs)
    assert first == second
    assert first["applied"] is False
    assert first["writes_performed"] is False
    assert first["llm_authority"] is False
