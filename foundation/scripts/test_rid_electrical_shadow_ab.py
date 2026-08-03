#!/usr/bin/env python3
"""Unit checks for shadow A/B helpers (no Master write)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

spec = importlib.util.spec_from_file_location(
    "rid_electrical_shadow_ab",
    FOUNDATION / "scripts" / "rid_electrical_shadow_ab.py",
)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> int:
    assert mod._pearson([1, 2, 3, 4], [2, 4, 6, 8]) is not None
    assert abs(float(mod._pearson([1, 2, 3, 4], [2, 4, 6, 8])) - 1.0) < 1e-9
    assert mod._mae([1.0, 2.0], [1.5, 2.5]) == 0.5
    a, b = mod._fit_blend([1, 2, 3, 4], [0, 0, 0, 0], [1, 2, 3, 4])
    assert abs(a - 1.0) < 1e-6
    assert abs(b) < 1e-6
    # Tiny live run — must not grant admission
    out = mod.run(samples=3, sleep_s=0.2)
    assert out["ok"] is True
    assert out["admission"]["granted"] is False
    assert out["admission"]["lane_advancement_eligible"] in (True, False)
    assert out["admission"]["supports_admission_review"] in (True, False)
    assert out["contract"]["isolated_strong_window_advances_lane"] is False
    assert out["contract"]["geom_reweight_is_evidence_of_info_gain"] is False
    assert out["lifecycle"] == "measured_in_shadow"
    assert out["runtime_health"]["electrical_in_master_subsystems"] is False
    assert out["verdict"] in {
        "INCONCLUSIVE",
        "INCONCLUSIVE_LOW_SIGNAL",
        "INCONCLUSIVE_CHANNEL_DEPENDENCE",
        "SHADOW_ONLY",
        "SHADOW_WINDOW_PASS",
    }
    print("PASS test_rid_electrical_shadow_ab")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
