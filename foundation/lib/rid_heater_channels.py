"""Heater-domain RID channels — observer for industrial temp control.

Maps process numbers (SP, PV, duty%, capacity, overtemp limit) onto RSR/LTP/RLE.
Does NOT replace PID. Feeds the RID supervisory layer above PID.
"""
from __future__ import annotations

import math
from typing import Any

from lib.master_rid import sn_from_channels


def _clamp01(x: float) -> float:
    if math.isnan(x) or math.isinf(x):
        return 0.0
    return max(0.0, min(1.0, float(x)))


def heater_rid_channels(
    *,
    setpoint: float,
    pv: float,
    duty_pct: float,
    temp_lo: float,
    temp_hi: float,
    overtemp_limit: float,
    capacity_pct: float = 100.0,
) -> dict[str, Any]:
    """Compute RSR/LTP/RLE/S_n for a heater loop.

    RSR — reconstruction: how well PV matches SP (tracking identity).
    LTP — capacity vs demand: heater capacity vs current duty demand.
    RLE — headroom: distance from PV to overtemp limit (thermal remaining).
    """
    span = max(temp_hi - temp_lo, 1.0)
    y = _clamp01((float(pv) - temp_lo) / span)
    recon = _clamp01((float(setpoint) - temp_lo) / span)
    # RSR: 1 - |PV - SP| / span (normalized tracking fidelity)
    rsr = _clamp01(1.0 - abs(float(pv) - float(setpoint)) / span)

    duty = max(0.0, min(100.0, float(duty_pct)))
    cap = max(float(capacity_pct), 1e-6)
    demand = max(duty, 1e-6)
    # LTP: capacity/demand capped at 1 (same units %)
    ltp = _clamp01(cap / demand) if demand > 0 else 1.0
    if duty < 1.0:
        ltp = 1.0  # idle demand = no capacity strain

    headroom = float(overtemp_limit) - float(pv)
    headroom_span = max(float(overtemp_limit) - temp_lo, 1.0)
    rle = _clamp01(headroom / headroom_span)

    sn = sn_from_channels(rsr, ltp, rle)
    worst = min((("RSR", rsr), ("LTP", ltp), ("RLE", rle)), key=lambda t: t[1])[0]
    return {
        "rsr": round(rsr, 6),
        "ltp": round(ltp, 6),
        "rle": round(rle, 6),
        "s_n": round(sn, 6),
        "worst_leg": worst,
        "norm_pv": round(y, 6),
        "norm_sp": round(recon, 6),
        "duty_pct": round(duty, 4),
        "headroom": round(headroom, 4),
    }
