#!/usr/bin/env python3
"""Unit checks for multi-window electrical admission gate."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_admission import (  # noqa: E402
    MIN_PASSING_WINDOWS,
    evaluate_multiwindow,
    window_passes_acceptance,
)


def _fake_report(
    *,
    at: datetime,
    duration_s: float,
    delta_info: float,
    master_var: float,
    valid: int = 20,
) -> dict:
    return {
        "at": at.isoformat(),
        "verdict": "SHADOW_WINDOW_PASS",
        "window": {"duration_s": duration_s, "valid_shadow_rows": valid},
        "dependence": {"master_s_n_variance": master_var},
        "delta_info": {"delta_info": delta_info},
        "geom_reweight": {"delta_mean": -0.05},
    }


def main() -> int:
    t0 = datetime(2026, 7, 26, 20, 0, 0, tzinfo=timezone.utc)
    # One strong isolated window — must NOT advance
    one = [
        _fake_report(at=t0, duration_s=30, delta_info=0.02, master_var=0.01),
    ]
    e1 = evaluate_multiwindow(one)
    assert e1["lane_advancement_eligible"] is False
    assert e1["supports_admission_review"] is False
    assert e1["lifecycle"] == "rejected_operational_use"
    assert e1["criteria"]["isolated_strong_window_advances_lane"] is False
    assert e1["criteria"]["advancement_permanently_closed"] is True

    # Three independent dynamic positive windows — historically would pass,
    # but lane advancement remains closed after decisive negative result.
    three = [
        _fake_report(
            at=t0 + timedelta(minutes=10 * i),
            duration_s=30,
            delta_info=0.02,
            master_var=0.01,
        )
        for i in range(MIN_PASSING_WINDOWS)
    ]
    e3 = evaluate_multiwindow(three)
    assert e3["historical_passing_independent_n"] == MIN_PASSING_WINDOWS
    assert e3["would_have_met_min_windows"] is True
    assert e3["passing_independent_n"] == 0
    assert e3["lane_advancement_eligible"] is False
    assert e3["supports_admission_review"] is False
    assert e3["admission_granted"] is False
    assert e3["lifecycle"] == "rejected_operational_use"

    # Flat Master fails window acceptance even with positive delta
    flat = window_passes_acceptance(
        _fake_report(at=t0, duration_s=30, delta_info=0.02, master_var=0.0)
    )
    assert flat["passes"] is False
    assert "master_not_sufficiently_dynamic" in flat["reasons"]

    # Geom-only (zero delta) fails
    geom = window_passes_acceptance(
        _fake_report(at=t0, duration_s=30, delta_info=0.0, master_var=0.01)
    )
    assert geom["passes"] is False

    print("PASS test_rid_electrical_admission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
