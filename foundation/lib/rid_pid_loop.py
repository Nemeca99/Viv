"""Closed-loop RID-on-PID run + metrics + A/B prove/disprove.

Baseline = PID alone.
Pilot    = RID layered on PID (gain schedule + RLE clamp + interlock).
Same plant, same gains, same setpoint profile. Machine-readable verdict.
"""
from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import ARTIFACTS
from lib.pid_controller import PIDGains
from lib.quartz_heater_plant import QuartzHeaterPlant
from lib.rid_pid_supervisor import RIDOnPIDController, RIDSupervisorConfig

AUDIT = ARTIFACTS / "audit"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunProfile:
    setpoint_c: float = 350.0
    duration_s: float = 120.0
    dt_s: float = 0.5
    # Step disturbance at this time (cold load)
    disturb_at_s: float = 60.0
    disturb_delta_c: float = -40.0
    initial_temp_c: float = 25.0


@dataclass
class RunMetrics:
    n: int = 0
    iae: float = 0.0
    overshoot_c: float = 0.0
    settling_s: float | None = None
    max_pv: float = 0.0
    min_rle: float = 1.0
    min_sn: float = 1.0
    interlock_trips: int = 0
    duty_clamps: int = 0
    mean_abs_error: float = 0.0
    final_error: float = 0.0


def _compute_metrics(rows: list[dict[str, Any]], profile: RunProfile) -> RunMetrics:
    if not rows:
        return RunMetrics()
    sp = float(profile.setpoint_c)
    iae = 0.0
    max_pv = max(float(r["pv"]) for r in rows)
    overshoot = max(0.0, max_pv - sp)
    min_rle = min(float((r.get("rid") or {}).get("rle") or 1.0) for r in rows)
    min_sn = min(float((r.get("rid") or {}).get("s_n") or 1.0) for r in rows)
    trips = sum(1 for r in rows if r.get("interlocked"))
    clamps = sum(1 for r in rows if "rle_duty_clamp" in (r.get("actions") or []))
    # Settling: first time |err| stays < 2°C for 10 consecutive samples after 20% of run
    band = 2.0
    settle = None
    need = max(3, int(10.0 / profile.dt_s))
    start_i = int(0.2 * len(rows))
    streak = 0
    for i, r in enumerate(rows):
        if i < start_i:
            continue
        if abs(float(r["pv"]) - sp) <= band:
            streak += 1
            if streak >= need and settle is None:
                settle = float(r["t"])
                break
        else:
            streak = 0
    for r in rows:
        iae += abs(float(r["pv"]) - sp) * float(profile.dt_s)
    mae = iae / max(profile.duration_s, 1e-6)
    return RunMetrics(
        n=len(rows),
        iae=round(iae, 4),
        overshoot_c=round(overshoot, 4),
        settling_s=None if settle is None else round(settle, 3),
        max_pv=round(max_pv, 4),
        min_rle=round(min_rle, 6),
        min_sn=round(min_sn, 6),
        interlock_trips=trips,
        duty_clamps=clamps,
        mean_abs_error=round(mae, 4),
        final_error=round(float(rows[-1]["pv"]) - sp, 4),
    )


def run_closed_loop(
    *,
    mode: str,
    profile: RunProfile | None = None,
    gains: PIDGains | None = None,
    rid_cfg: RIDSupervisorConfig | None = None,
    plant: QuartzHeaterPlant | None = None,
) -> dict[str, Any]:
    profile = profile or RunProfile()
    gains = gains or PIDGains(kp=1.8, ki=0.08, kd=3.5, out_max=100.0)
    rid_cfg = rid_cfg or RIDSupervisorConfig(
        temp_lo=0.0,
        temp_hi=600.0,
        overtemp_limit=480.0,  # aggressive headroom for software stress test
    )
    plant = plant or QuartzHeaterPlant()
    plant.reset(profile.initial_temp_c)

    ctrl = RIDOnPIDController(base_gains=deepcopy(gains), rid=deepcopy(rid_cfg), mode=mode)
    ctrl.reset()

    rows: list[dict[str, Any]] = []
    t = 0.0
    disturbed = False
    while t < profile.duration_s - 1e-9:
        if (not disturbed) and t >= profile.disturb_at_s:
            plant.set_disturbance(profile.disturb_delta_c)
            disturbed = True
        out = ctrl.step(setpoint=profile.setpoint_c, pv=plant.pv, dt=profile.dt_s)
        plant.step(out["duty_pct"], profile.dt_s)
        row = {
            "t": round(t, 4),
            "setpoint": profile.setpoint_c,
            "pv": plant.pv,
            "true_temp": plant._true_temp,
            "duty_pct": out["duty_pct"],
            "pid_duty_pct": out["pid_duty_pct"],
            "rid": out["rid"],
            "actions": out["actions"],
            "interlocked": out["interlocked"],
            "mode": mode,
        }
        rows.append(row)
        t += profile.dt_s

    metrics = _compute_metrics(rows, profile)
    return {
        "mode": mode,
        "profile": asdict(profile),
        "gains": asdict(gains),
        "rid_cfg": asdict(rid_cfg),
        "metrics": asdict(metrics),
        "rows": rows,
        "n_rows": len(rows),
    }


def ab_compare(
    *,
    profile: RunProfile | None = None,
    gains: PIDGains | None = None,
    rid_cfg: RIDSupervisorConfig | None = None,
    min_samples: int = 50,
) -> dict[str, Any]:
    """Baseline PID vs pilot RID+PID. Verdict: PROVED / DISPROVED / INCONCLUSIVE."""
    profile = profile or RunProfile()
    gains = gains or PIDGains(kp=1.8, ki=0.08, kd=3.5)
    rid_cfg = rid_cfg or RIDSupervisorConfig(temp_lo=0.0, temp_hi=600.0, overtemp_limit=480.0)

    baseline = run_closed_loop(mode="pid", profile=profile, gains=gains, rid_cfg=rid_cfg)
    pilot = run_closed_loop(mode="rid_pid", profile=profile, gains=gains, rid_cfg=rid_cfg)

    bm = baseline["metrics"]
    pm = pilot["metrics"]
    valid = bm["n"] >= min_samples and pm["n"] >= min_samples

    deltas = {
        "iae": round(pm["iae"] - bm["iae"], 4),
        "overshoot_c": round(pm["overshoot_c"] - bm["overshoot_c"], 4),
        "mean_abs_error": round(pm["mean_abs_error"] - bm["mean_abs_error"], 4),
        "min_rle": round(pm["min_rle"] - bm["min_rle"], 6),
        "min_sn": round(pm["min_sn"] - bm["min_sn"], 6),
        "interlock_trips": pm["interlock_trips"] - bm["interlock_trips"],
        "duty_clamps": pm["duty_clamps"] - bm["duty_clamps"],
    }

    # Prove = RID+PID better or equal tracking AND better thermal safety (higher min RLE or less overshoot)
    # Disprove = RID+PID worse tracking without safety benefit
    if not valid:
        verdict = "INCONCLUSIVE"
        reason = "insufficient_samples"
    else:
        tracking_ok = deltas["iae"] <= 0.0 or abs(deltas["iae"]) / max(bm["iae"], 1e-6) < 0.05
        tracking_better = deltas["iae"] < 0.0
        tracking_worse = deltas["iae"] > max(5.0, 0.1 * bm["iae"])
        safety_better = deltas["overshoot_c"] < 0.0 or deltas["min_rle"] > 0.0
        safety_worse = deltas["overshoot_c"] > 1.0 and deltas["min_rle"] < 0.0

        if tracking_worse and not safety_better:
            verdict = "DISPROVED"
            reason = "worse_tracking_no_safety_gain"
        elif (tracking_better or tracking_ok) and safety_better:
            verdict = "PROVED"
            reason = "tracking_ok_and_safety_improved"
        elif tracking_ok and not safety_worse:
            verdict = "INCONCLUSIVE"
            reason = "no_clear_safety_delta"
        else:
            verdict = "DISPROVED"
            reason = "net_regression"

    report = {
        "experiment_id": "ab_rid_pid_heater_v1",
        "timestamp": _utc(),
        "contract": "RID layers on PID — never replaces PID",
        "verdict": verdict,
        "reason": reason,
        "valid_sample": valid,
        "min_samples": min_samples,
        "baseline": {"mode": "pid", "metrics": bm},
        "pilot": {"mode": "rid_pid", "metrics": pm},
        "deltas_pilot_minus_baseline": deltas,
        "profile": asdict(profile),
        "note": "Software plant. Swap plant for hardware IO when heater+PID arrive.",
    }
    return report


def write_ab_report(report: dict[str, Any], out_dir: Path | None = None) -> tuple[Path, Path]:
    out_dir = out_dir or AUDIT
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath = out_dir / "ab_rid_pid_heater_v1.json"
    mpath = out_dir / "ab_rid_pid_heater_v1.md"
    jpath.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    b = report["baseline"]["metrics"]
    p = report["pilot"]["metrics"]
    d = report["deltas_pilot_minus_baseline"]
    md = f"""# A/B: RID-on-PID Heater (`ab_rid_pid_heater_v1`)

**Verdict:** {report["verdict"]} ({report["reason"]})  
**Generated:** {report["timestamp"]}  
**Contract:** RID layers on PID — never replaces PID.

## Baseline (PID alone)

| Metric | Value |
|--------|-------|
| IAE | {b["iae"]} |
| Overshoot °C | {b["overshoot_c"]} |
| Mean abs error | {b["mean_abs_error"]} |
| Min RLE | {b["min_rle"]} |
| Min S_n | {b["min_sn"]} |

## Pilot (RID on PID)

| Metric | Value |
|--------|-------|
| IAE | {p["iae"]} |
| Overshoot °C | {p["overshoot_c"]} |
| Mean abs error | {p["mean_abs_error"]} |
| Min RLE | {p["min_rle"]} |
| Min S_n | {p["min_sn"]} |
| Duty clamps | {p["duty_clamps"]} |
| Interlock trips | {p["interlock_trips"]} |

## Deltas (pilot − baseline)

- IAE: {d["iae"]}
- overshoot_c: {d["overshoot_c"]}
- min_rle: {d["min_rle"]}
- min_sn: {d["min_sn"]}

Lower IAE / overshoot and higher min RLE support **PROVED**. Clear tracking regression without safety gain → **DISPROVED**.
"""
    mpath.write_text(md, encoding="utf-8")
    return jpath, mpath
