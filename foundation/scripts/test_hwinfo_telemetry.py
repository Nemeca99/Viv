#!/usr/bin/env python3
"""Honesty tests for HWiNFO CSV electrical admission + Ohm i_gpu."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.hwinfo_telemetry import (  # noqa: E402
    I_GPU_ORIGIN_OHM,
    REFUSED_COLUMNS,
    read_electrical,
)
from lib.rid_electrical import reject_derived_live_axes, triad_availability  # noqa: E402


FIXTURE_HEADER = (
    "Date,Time,"
    '"CPU Package Power [W]",'
    '"Vcore [V]",'
    '"VR VCC Current (SVID IOUT) [A]",'
    '"GPU Power [W]",'
    '"GPU Core Voltage [V]",'
    '"GPU PCIe +12V Input Power [W]",'
    '"GPU PCIe +12V Input Voltage [V]",'
    '"GPU 8-pin #1 Input Power [W]",'
    '"GPU 8-pin #1 Input Voltage [V]",'
    '"+12V [V]",'
    '"Current (IOUT) [A]"'
)
# P_pcie=4.088 V=12.060 → 0.33897; P_8pin=15.811 V=12.051 → 1.31199; sum≈1.65096
FIXTURE_ROW = (
    "26.7.2026,20:36:12.995,98.968,1.212,67.735,20.618,0.662,"
    "4.088,12.060,15.811,12.051,0.048,72.000"
)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "hwinfo.CSV"
        path.write_text(FIXTURE_HEADER + "\n" + FIXTURE_ROW + "\n", encoding="utf-8")
        row = read_electrical(path)
        assert row["ok"] is True
        assert abs(float(row["w_cpu"]) - 98.968) < 1e-6
        assert abs(float(row["v_cpu"]) - 1.212) < 1e-6
        assert abs(float(row["i_cpu"]) - 67.735) < 1e-6
        assert abs(float(row["w_gpu"]) - 20.618) < 1e-6
        assert abs(float(row["v_gpu"]) - 0.662) < 1e-6
        assert row["i_gpu"] is not None
        assert abs(float(row["i_gpu"]) - (4.088 / 12.060 + 15.811 / 12.051)) < 1e-6
        assert row["origins"]["i_gpu"] == I_GPU_ORIGIN_OHM
        assert row["independent_axes"]["i_gpu"] is False
        assert "+12V [V]" in REFUSED_COLUMNS
        assert "Current (IOUT) [A]" in REFUSED_COLUMNS

        # Independence still denied for Ohm-derived current
        guard = reject_derived_live_axes(
            w=20.618,
            v=12.0,
            i=row["i_gpu"],
            i_was_derived_from_w_over_v=True,
        )
        assert guard["admissible_as_independent_axis"] is False

        # Observe triad may complete with reconstructed i_gpu numbers
        triad = triad_availability(
            w_cpu=row["w_cpu"],
            w_gpu=row["w_gpu"],
            v_cpu=row["v_cpu"],
            v_gpu=row["v_gpu"],
            i_cpu=row["i_cpu"],
            i_gpu=row["i_gpu"],
        )
        assert triad["available"] is True
        assert triad["s_electrical"] is not None

        # Incomplete rails → no i_gpu invent
        header_no_v = (
            "Date,Time,"
            '"GPU PCIe +12V Input Power [W]",'
            '"GPU 8-pin #1 Input Power [W]"'
        )
        path2 = Path(td) / "no_v.CSV"
        path2.write_text(header_no_v + "\n26.7.2026,20:00:00,4.0,15.0\n", encoding="utf-8")
        row2 = read_electrical(path2)
        assert row2["i_gpu"] is None

    missing = read_electrical(
        Path(tempfile.gettempdir()) / "viv_hwinfo_missing_does_not_exist.CSV"
    )
    assert missing["ok"] is False
    assert missing["w_cpu"] is None
    assert missing["error"] == "csv_not_found"

    print("PASS test_hwinfo_telemetry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
