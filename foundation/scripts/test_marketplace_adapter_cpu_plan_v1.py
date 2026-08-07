"""Adapter tests for the optional marketplace boundary."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.aios_adapter_marketplace import cpu_plan, run_smoke, status


def test_status_and_smoke() -> None:
    assert status()["ok"] is True
    smoke = run_smoke()
    assert smoke["ok"] is True
    assert smoke["plan"]["install_plan"]["install_authorized"] is False
    assert smoke["plan"]["installation_performed"] is False


def test_plan_is_repeatable() -> None:
    catalog = [{"name": "data_core", "description": "Data", "version": "1.0.0", "license": "MIT"}]
    first = cpu_plan(catalog, query="data")
    second = cpu_plan(catalog, query="data")
    assert first == second
    assert first["writes_performed"] is False
    assert first["llm_authority"] is False
