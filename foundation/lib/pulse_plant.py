"""Pulse game — bounded CPU load burst; she predicts what it does to the plant.

Same PRT contract as life: see the pulse parameters BEFORE predicting, commit
triad + task scalar (mean cpu load during burst), then physics grades both.
Real telemetry only. Bounded and contained: duty <= 0.5, seconds <= 15.
"""
from __future__ import annotations

import time
from typing import Any

try:
    import psutil
except ImportError as exc:
    raise SystemExit("pulse_plant requires psutil") from exc

MAX_DUTY = 0.5
MAX_SECONDS = 15.0
MAX_CORES = 8

# Rotate difficulty like pick_pressure_pattern does for life
PULSE_LEVELS: list[dict[str, float]] = [
    {"duty": 0.20, "seconds": 8.0, "cores": 2},
    {"duty": 0.35, "seconds": 10.0, "cores": 4},
    {"duty": 0.45, "seconds": 10.0, "cores": 4},
    {"duty": 0.30, "seconds": 12.0, "cores": 6},
    {"duty": 0.50, "seconds": 8.0, "cores": 2},
]


def pick_pulse_level(round_i: int = 0) -> dict[str, float]:
    return dict(PULSE_LEVELS[int(round_i) % len(PULSE_LEVELS)])


def clamp_pulse_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "duty": max(0.05, min(MAX_DUTY, float(cfg.get("duty") or 0.3))),
        "seconds": max(2.0, min(MAX_SECONDS, float(cfg.get("seconds") or 10.0))),
        "cores": int(max(1, min(MAX_CORES, int(cfg.get("cores") or 4)))),
    }


def peek_before(cfg: dict[str, Any]) -> dict[str, Any]:
    """Pre-act view for the predict prompt (honest task, like life peek_before)."""
    c = clamp_pulse_cfg(cfg)
    return {
        "duty": c["duty"],
        "seconds": c["seconds"],
        "cores": c["cores"],
        "baseline_load_pct": float(psutil.cpu_percent(interval=0.5)),
        "total_cores": int(psutil.cpu_count(logical=True) or 8),
    }


def run_pulse(cfg: dict[str, Any]) -> dict[str, Any]:
    """Run the bounded burst, sampling real load each second. Always stops fleet."""
    from lib.growth_plant_pressure import PlantPressure

    c = clamp_pulse_cfg(cfg)
    baseline = float(psutil.cpu_percent(interval=0.5))
    loads: list[float] = []
    pressure = PlantPressure(cores=int(c["cores"]), duty=float(c["duty"]))
    t0 = time.time()
    try:
        pressure.start()
        while time.time() - t0 < float(c["seconds"]):
            loads.append(float(psutil.cpu_percent(interval=1.0)))
    finally:
        pressure.stop()
    elapsed = round(time.time() - t0, 2)
    if not loads:
        return {"ok": False, "reason": "no_samples", **c}
    mean_load = round(sum(loads) / len(loads), 2)
    return {
        "ok": True,
        **c,
        "baseline_load_pct": baseline,
        "mean_load_pct": mean_load,
        "peak_load_pct": round(max(loads), 2),
        "samples": len(loads),
        "elapsed_s": elapsed,
    }


def prior_mean_load(before: dict[str, Any]) -> float:
    """Curriculum prior: baseline + duty * cores/total headroom share of 100%."""
    base = float(before.get("baseline_load_pct") or 10.0)
    duty = float(before.get("duty") or 0.3)
    cores = float(before.get("cores") or 4)
    total = float(before.get("total_cores") or 8)
    est = base + duty * (cores / max(total, 1.0)) * 100.0
    return round(max(0.0, min(100.0, est)), 2)


def score_mean_load(
    predicted: float | None,
    actual: float,
    *,
    reward_frac: float = 0.15,
    punish_frac: float = 0.40,
) -> dict[str, Any] | None:
    """Fractional-error grade on the load scalar (mirrors score_live_cells)."""
    if predicted is None:
        return None
    actual_f = max(0.0, float(actual))
    pred_f = max(0.0, float(predicted))
    denom = max(1.0, actual_f)
    frac = abs(pred_f - actual_f) / denom
    if frac <= reward_frac:
        label = "REWARD"
    elif frac >= punish_frac:
        label = "PUNISH"
    else:
        label = "NEUTRAL"
    return {
        "predicted": round(pred_f, 2),
        "actual": round(actual_f, 2),
        "frac_error": round(frac, 6),
        "label": label,
        "reward_frac": reward_frac,
        "punish_frac": punish_frac,
    }
