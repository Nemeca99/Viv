"""Adapter regression tests for game_core."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.aios_adapter_game import cpu_plan, run_smoke, status


def test_status_and_smoke() -> None:
    assert status()["ok"] is True
    smoke = run_smoke()
    assert smoke["ok"] is True
    assert smoke["plan"]["event_intent"]["applied"] is False
    assert smoke["plan"]["choice_candidates"]["master_s_n_changed"] is False


def test_plan_is_repeatable() -> None:
    sessions = [{"session_id": "s1", "game": "Example", "events": [{"type": "win", "data": {"strategy": "wait"}}]}]
    first = cpu_plan(sessions, game_name="Example")
    second = cpu_plan(sessions, game_name="Example")
    assert first == second
    assert first["writes_performed"] is False
    assert first["llm_authority"] is False
