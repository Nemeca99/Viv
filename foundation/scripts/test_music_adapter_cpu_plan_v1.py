"""Adapter tests for the optional music boundary."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.aios_adapter_music import cpu_plan, run_smoke, status


def test_status_and_smoke() -> None:
    assert status()["ok"] is True
    smoke = run_smoke()
    assert smoke["ok"] is True
    assert smoke["plan"]["playback_started"] is False
    assert smoke["plan"]["play_intent"]["playback_authorized"] is False


def test_plan_is_repeatable() -> None:
    library = [{"artist": "A", "album": "B", "genre": "jazz", "mood": "calm"}]
    first = cpu_plan(library, [], mood="calm", play_intent=True)
    second = cpu_plan(library, [], mood="calm", play_intent=True)
    assert first == second
    assert first["writes_performed"] is False
    assert first["llm_authority"] is False
