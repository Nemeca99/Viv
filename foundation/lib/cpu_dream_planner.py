"""Deterministic, read-only planning for governed dream consolidation."""
from __future__ import annotations

from typing import Any

MANUAL_SOURCE = "F:/AIOS_Clean/dream_core"
MIN_SN = 0.37
HOT_PULSE_BPM = 0.75


def plan_dream_cycle(*, s_n: float, live_chars: int, pulse_bpm: float | None = None, force: bool = False, min_live_chars: int = 80) -> dict[str, Any]:
    """Choose a bounded consolidation mode without reading or writing state."""
    sn = max(0.0, min(float(s_n), 1.0))
    chars = max(0, int(live_chars))
    pulse = None if pulse_bpm is None else max(0.0, float(pulse_bpm))
    if sn < MIN_SN and not force:
        allowed, reason = False, "s_n_dormancy"
    elif chars < max(0, int(min_live_chars)) and not force:
        allowed, reason = False, "thin_live_memory"
    else:
        allowed, reason = True, "forced" if force else "ready"
    mode = "hot_path" if pulse is not None and pulse >= HOT_PULSE_BPM else "cold_path"
    return {
        "ok": True, "allowed": allowed, "reason": reason, "mode": mode,
        "s_n": sn, "live_chars": chars, "pulse_bpm": pulse,
        "bounded": True, "writes_performed": False, "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
    }
