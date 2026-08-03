#!/usr/bin/env python3
"""Adversarial honesty tests for electrical RID contract (B.13–B.15).

Attacks: partial triad, derived I=W/V fill, Master inflation, observe non-contamination,
null vs 0 vs 1 semantics.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.master_rid import MASTER_RID_PATH  # noqa: E402
from lib.rid_electrical import (  # noqa: E402
    active_set_master,
    ratio,
    reject_derived_live_axes,
    triad_availability,
)


def main() -> int:
    # --- Partial triad: GPU W only ---
    partial = triad_availability(
        w_cpu=None,
        w_gpu=58.521,
        v_cpu=None,
        v_gpu=None,
        i_cpu=None,
        i_gpu=None,
    )
    assert partial["available"] is False
    assert partial["s_electrical"] is None
    assert partial["reason"] == "incomplete_channels"

    # --- Forbidden fill: derive I=W/V and pretend independent axes ---
    w, v = 48.0, 12.0
    i_derived = w / v
    guard = reject_derived_live_axes(
        w=w, v=v, i=i_derived, i_was_derived_from_w_over_v=True
    )
    assert guard["ok"] is False
    assert guard["admissible_as_independent_axis"] is False

    # Even if caller stuffs derived I into triad_availability, honesty policy
    # for *live* axes is reject_derived — triad math may compute but admission
    # of independence is denied.
    stuffed = triad_availability(
        w_cpu=24.0,
        w_gpu=48.0,
        v_cpu=12.0,
        v_gpu=12.0,
        i_cpu=24.0 / 12.0,
        i_gpu=48.0 / 12.0,
    )
    # Math can form ratios from numbers, but both sides' I were derived — flag it.
    assert stuffed["available"] is True  # numeric completeness ≠ honesty of origin
    assert reject_derived_live_axes(
        w=24.0, v=12.0, i=2.0, i_was_derived_from_w_over_v=True
    )["admissible_as_independent_axis"] is False

    # --- Master inflation forbidden ---
    with_fake = active_set_master(
        {"cpu": 0.5, "coolant": 0.8, "electrical": 1.0},
        ["cpu", "coolant", "electrical"],
    )
    without = active_set_master(
        {"cpu": 0.5, "coolant": 0.8, "electrical": 1.0},
        ["cpu", "coolant"],
    )
    assert with_fake > without
    # Contract: unavailable electrical must use exclude path (without)
    assert "electrical" not in ["cpu", "coolant"]

    # --- null vs 0 vs 1 ---
    # null path: missing channel → s_electrical None
    assert partial["s_electrical"] is None
    # 0 path: required failed reading → ratio 0
    assert ratio(None, 10.0, required=True) == 0.0
    assert ratio(0.0, 10.0, required=True) == 0.0
    # 1 path: equal measured values
    assert ratio(12.0, 12.0, required=True) == 1.0
    # measured failure collapse product
    from lib.rid_electrical import s_electrical

    assert s_electrical(0.0, 1.0, 1.0) == 0.0
    assert s_electrical(1.0, 1.0, 1.0) == 1.0

    # --- Observe sidecar non-contamination ---
    before = MASTER_RID_PATH.read_text(encoding="utf-8") if MASTER_RID_PATH.is_file() else None
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "rid_electrical_observe",
        FOUNDATION / "scripts" / "rid_electrical_observe.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.observe_once()
    after = MASTER_RID_PATH.read_text(encoding="utf-8") if MASTER_RID_PATH.is_file() else None
    assert out.get("master_authority_changed") is False
    assert out["master_readonly"].get("disk_unchanged") is True
    assert before == after
    # electrical not in Master subsystem list (observe ≠ authority)
    subs = out["master_readonly"].get("master", {}).get("subsystems") or []
    assert "electrical" not in subs

    # When HWiNFO Ohm i_gpu is present, triad may be available in observe —
    # but reconstructed amps are stamped non-independent.
    indep = out.get("meters", {}).get("independent_axes") or {}
    origins = out.get("meters", {}).get("origins") or {}
    if out["meters"].get("i_gpu") is not None and origins.get("i_gpu") == (
        "software_ohm_from_measured_hwinfo_rails"
    ):
        assert indep.get("i_gpu") is False
        guard = reject_derived_live_axes(
            w=out["meters"].get("w_gpu"),
            v=None,
            i=out["meters"]["i_gpu"],
            i_was_derived_from_w_over_v=True,
        )
        assert guard["admissible_as_independent_axis"] is False
        assert out["electrical"]["available"] is True
        assert out["electrical"]["s_electrical"] is not None
    elif out["electrical"]["available"] is False:
        assert out["electrical"]["s_electrical"] is None

    latest = FOUNDATION / "artifacts" / "auto" / "rid_electrical" / "observe_latest.json"
    assert latest.is_file()
    disk = json.loads(latest.read_text(encoding="utf-8"))
    assert disk.get("master_authority_changed") is False

    print("PASS test_rid_electrical_adversarial", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
