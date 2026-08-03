#!/usr/bin/env python3
"""Contract tests for RID electrical math — no invented live meters."""
from __future__ import annotations

import math
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical import (  # noqa: E402
    active_set_master,
    choose_route,
    coupling_product,
    ohm_consistent,
    ratio,
    rle_identity,
    routing_score,
    s_electrical,
    triad_availability,
    weighted_geom_mean,
)


def _approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(float(a) - float(b)) <= tol


def main() -> int:
    # 1) RLE identity
    for a, b in ((40.0, 42.0), (42.0, 42.0), (30.0, 50.0)):
        idn = rle_identity(a, b)
        assert _approx(idn["residual"], 0.0), idn

    # 2) Mixed-domain illustrative C/S (docs numbers)
    r_w = 65.0 / 120.0
    r_v = 1.0
    r_i = 2.0 / 4.0
    c = coupling_product(r_w, r_v, r_i)
    s = s_electrical(r_w, r_v, r_i)
    assert _approx(c, 0.2708333333, tol=1e-6), c
    assert _approx(s, 0.646995, tol=1e-4), s

    # 3) Ohm-consistent fixture: shared V => r_W == r_I
    v = 12.0
    i_cpu, i_gpu = 2.0, 4.0
    w_cpu, w_gpu = v * i_cpu, v * i_gpu
    assert ohm_consistent(w_cpu, v, i_cpu)
    assert ohm_consistent(w_gpu, v, i_gpu)
    assert _approx(ratio(w_cpu, w_gpu), ratio(i_cpu, i_gpu))
    assert _approx(ratio(v, v), 1.0)
    c_ohm = coupling_product(0.5, 1.0, 0.5)
    assert _approx(c_ohm, 0.25)
    assert _approx(s_electrical(0.5, 1.0, 0.5), 0.25 ** (1.0 / 3.0))

    # 4) Mixed-domain is NOT Ohm-consistent on one side with shared V story
    assert not ohm_consistent(65.0, 12.0, 2.0)
    assert not ohm_consistent(120.0, 12.0, 4.0)

    # 5) Inactive include inflates Master vs exclude
    inflated = active_set_master(
        {"cpu": 0.5, "coolant": 0.8, "electrical": 1.0},
        ["cpu", "coolant", "electrical"],
    )
    excluded = active_set_master(
        {"cpu": 0.5, "coolant": 0.8, "electrical": 1.0},
        ["cpu", "coolant"],
    )
    assert inflated > excluded
    assert _approx(inflated, (0.5 * 0.8 * 1.0) ** (1.0 / 3.0), tol=1e-4)
    assert _approx(excluded, (0.5 * 0.8) ** 0.5, tol=1e-4)

    # 6) Weighted geom mean
    wgm = weighted_geom_mean([0.9, 0.6, 0.8], [2.0, 1.0, 1.0])
    expected = math.exp((2 * math.log(0.9) + math.log(0.6) + math.log(0.8)) / 4.0)
    assert _approx(wgm, expected, tol=1e-9)

    # 7) Routing: eps required; delta<=0 => +inf preference
    try:
        choose_route({"cpu": (1.0, 0.1)}, eps=0.0)
        raise AssertionError("expected ValueError for eps<=0")
    except ValueError as exc:
        assert "routing_eps_must_be_positive" in str(exc)

    assert math.isinf(routing_score(10.0, 0.0))
    assert math.isinf(routing_score(10.0, -0.01))
    scored = routing_score(10.0, 0.2, eps=1e-6)
    assert _approx(scored, 50.0)
    # near-zero positive delta clamps to eps
    near = routing_score(1.0, 1e-12, eps=1e-6)
    assert _approx(near, 1.0 / 1e-6)

    picked = choose_route(
        {"cpu": (5.0, 0.1), "gpu": (8.0, 0.5)},
        eps=1e-6,
    )
    assert picked["choice"] == "cpu"  # 5/0.1=50 > 8/0.5=16

    # 8) Incomplete triad fail-closed (GPU watts only)
    inv = triad_availability(
        w_cpu=None,
        w_gpu=40.0,
        v_cpu=None,
        v_gpu=None,
        i_cpu=None,
        i_gpu=None,
    )
    assert inv["available"] is False
    assert inv["s_electrical"] is None
    assert "w_cpu" in inv["missing_channels"]
    assert inv["can_compute"]["r_w"] is False

    # Complete synthetic triad (fixtures, not live plant)
    full = triad_availability(
        w_cpu=24.0,
        w_gpu=48.0,
        v_cpu=12.0,
        v_gpu=12.0,
        i_cpu=2.0,
        i_gpu=4.0,
    )
    assert full["available"] is True
    assert full["s_electrical"] is not None
    assert _approx(float(full["r_w"]), 0.5)
    assert _approx(float(full["r_i"]), 0.5)

    # 9) ratio piecewise
    assert _approx(ratio(0.0, 0.0, required=True), 0.0)
    assert _approx(ratio(0.0, 0.0, required=False, both_intentionally_inactive=True), 1.0)
    assert _approx(ratio(None, 10.0, required=True), 0.0)

    print("PASS test_rid_electrical", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
