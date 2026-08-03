#!/usr/bin/env python3
"""Regression contracts for live-vs-stale piston telemetry."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib import master_rid  # noqa: E402


def _fake_state(*, now_s: float, age_s: float) -> Mock:
    path = Mock()
    path.is_file.return_value = True
    path.stat.return_value = SimpleNamespace(st_mtime=now_s - age_s)
    path.read_text.return_value = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "cores": [{"rsr": 0.8, "ltp": 0.8, "rle": 0.8, "s_n": 0.8}],
        }
    )
    return path


def main() -> int:
    assert master_rid.piston_state_is_fresh(0.0)
    assert master_rid.piston_state_is_fresh(master_rid.PISTON_STATE_MAX_AGE_S)
    assert not master_rid.piston_state_is_fresh(
        master_rid.PISTON_STATE_MAX_AGE_S + 0.001
    )
    assert not master_rid.piston_state_is_fresh(
        -master_rid.TELEMETRY_CLOCK_SKEW_S - 0.001
    )
    assert not master_rid.piston_state_is_fresh(math.inf)
    assert not master_rid.piston_state_is_fresh(math.nan)

    now_s = 1_767_225_600.0  # 2026-01-01T00:00:00Z
    fresh = _fake_state(now_s=now_s, age_s=30.0)
    with (
        patch.object(master_rid, "PISTON_STATE_PATH", fresh),
        patch.object(master_rid.time, "time", return_value=now_s),
    ):
        fresh_result = master_rid.subsystem_piston()
    assert fresh_result.available

    stale = _fake_state(
        now_s=now_s, age_s=master_rid.PISTON_STATE_MAX_AGE_S + 1.0
    )
    with (
        patch.object(master_rid, "PISTON_STATE_PATH", stale),
        patch.object(master_rid.time, "time", return_value=now_s),
    ):
        stale_result = master_rid.subsystem_piston()
    assert not stale_result.available
    assert stale_result.source.startswith("stale:")

    print(
        json.dumps(
            {
                "ok": True,
                "fresh_available": fresh_result.available,
                "stale_available": stale_result.available,
                "max_age_s": master_rid.PISTON_STATE_MAX_AGE_S,
                "clock_skew_s": master_rid.TELEMETRY_CLOCK_SKEW_S,
                "negative_contracts": 6,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
