#!/usr/bin/env python3
"""Calibrated action-cost ledger from rail power (not Master S_n / routing).

Milestone path:
  validated integration → per-action attribution → repeatable cost profiles
  → (later) direct energy-outcome prediction

  E_gross = ∫ P(t) dt
  E_net   = E_gross - P_idle_baseline * Δt

Authority: accounting / informational only. Never enters A(t) or Master.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Sequence

# --- Accounting tolerances / defaults ---
SANITY_REL_TOL = 0.08  # |E - P_mean*Δt| / max(|E|,|PΔt|,1) ≤ this → agree
STALE_SENSOR_S = 5.0
MAX_GAP_WARN_S = 3.0
MIN_COVERAGE = 0.85
WARN_W_DEFAULT = 250.0
CRITICAL_W_DEFAULT = 400.0
WARN_MIN_DURATION_S = 3.0  # hysteresis: P>threshold for ≥ τ

IDLE_PHASE_NAMES = frozenset({"idle", "cooldown"})
IDLE_BASELINE_PHASES = frozenset({"idle"})  # cooldown is recovery, not idle baseline
ACTIVE_PHASE_HINT = frozenset(
    {"ramp", "sustained", "load", "equilibrate", "cpu_a", "cpu_b", "gpu_a", "gpu_b"}
)


def _finite(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def board_power_w(sample: dict[str, Any]) -> float | None:
    """CPU + GPU package watts when both present; else whichever is available."""
    pr = sample.get("P_rails") or {}
    w_cpu = _finite(pr.get("w_cpu"))
    w_gpu = _finite(pr.get("w_gpu"))
    if w_cpu is not None and w_gpu is not None:
        return w_cpu + w_gpu
    if w_cpu is not None:
        return w_cpu
    if w_gpu is not None:
        return w_gpu
    return None


def _pcie_pin8(sample: dict[str, Any]) -> tuple[float | None, float | None]:
    pr = sample.get("P_rails") or {}
    return _finite(pr.get("pcie_w")), _finite(pr.get("pin8_w"))


def integrate_energy_j(
    times_s: Sequence[float],
    powers_w: Sequence[float],
) -> dict[str, Any]:
    """Trapezoidal ∫ P dt in joules."""
    n = min(len(times_s), len(powers_w))
    if n < 2:
        return {
            "E_j": None,
            "n": n,
            "duration_s": None,
            "ok": False,
            "reason": "need_at_least_two_samples",
            "method": "trapezoidal",
            "largest_gap_s": None,
            "mean_cadence_s": None,
        }
    t = [float(times_s[i]) for i in range(n)]
    p = [float(powers_w[i]) for i in range(n)]
    if any(math.isnan(x) or math.isinf(x) for x in t + p):
        return {
            "E_j": None,
            "n": n,
            "duration_s": None,
            "ok": False,
            "reason": "non_finite",
            "method": "trapezoidal",
            "largest_gap_s": None,
            "mean_cadence_s": None,
        }
    if any(t[i] > t[i + 1] for i in range(n - 1)):
        return {
            "E_j": None,
            "n": n,
            "duration_s": None,
            "ok": False,
            "reason": "time_not_monotonic",
            "method": "trapezoidal",
            "largest_gap_s": None,
            "mean_cadence_s": None,
        }
    e = 0.0
    gaps = []
    for i in range(n - 1):
        dt = t[i + 1] - t[i]
        gaps.append(dt)
        e += 0.5 * (p[i] + p[i + 1]) * dt
    return {
        "E_j": e,
        "n": n,
        "duration_s": t[-1] - t[0],
        "ok": True,
        "method": "trapezoidal",
        "largest_gap_s": max(gaps) if gaps else None,
        "mean_cadence_s": (sum(gaps) / len(gaps)) if gaps else None,
    }


def peak_power_w(powers_w: Sequence[float]) -> float | None:
    vals = [float(x) for x in powers_w if _finite(x) is not None]
    if not vals:
        return None
    return max(vals)


def _quality_and_confidence(
    *,
    n_raw: int,
    n_power: int,
    n_missing_power: int,
    n_stale: int,
    largest_gap_s: float | None,
    cadence_s: float | None,
    E_gross: float | None,
    P_mean: float | None,
    duration_s: float | None,
    sanity_rel_tol: float = SANITY_REL_TOL,
) -> dict[str, Any]:
    coverage = (n_power / n_raw) if n_raw > 0 else 0.0
    stale_frac = (n_stale / n_raw) if n_raw > 0 else 0.0
    e_from_mean = None
    sanity_rel = None
    sanity_ok = None
    if (
        E_gross is not None
        and P_mean is not None
        and duration_s is not None
        and duration_s > 0
    ):
        e_from_mean = P_mean * duration_s
        denom = max(abs(E_gross), abs(e_from_mean), 1.0)
        sanity_rel = abs(E_gross - e_from_mean) / denom
        sanity_ok = sanity_rel <= sanity_rel_tol

    reasons: list[str] = []
    if n_power < 2:
        reasons.append("too_few_power_samples")
    if coverage < MIN_COVERAGE:
        reasons.append("low_coverage")
    if largest_gap_s is not None and largest_gap_s > MAX_GAP_WARN_S:
        reasons.append("large_timestamp_gap")
    if stale_frac > 0.25:
        reasons.append("many_stale_sensors")
    if sanity_ok is False:
        reasons.append("sanity_E_vs_Pmean_dt_mismatch")

    if n_power < 2 or coverage < 0.5 or sanity_ok is False and E_gross is not None:
        status = "invalid"
    elif reasons:
        status = "degraded"
    else:
        status = "valid"

    return {
        "sample_coverage_pct": round(100.0 * coverage, 2),
        "n_raw_samples": n_raw,
        "n_power_samples": n_power,
        "n_missing_power": n_missing_power,
        "n_stale_sensors": n_stale,
        "stale_sensor_frac": round(stale_frac, 4),
        "largest_timestamp_gap_s": largest_gap_s,
        "integration_cadence_s": cadence_s,
        "E_from_Pmean_dt_j": e_from_mean,
        "sanity_rel_err": sanity_rel,
        "sanity_rel_tol": sanity_rel_tol,
        "sanity_ok": sanity_ok,
        "confidence": status,
        "confidence_reasons": reasons,
    }


def idle_baseline_w(
    samples: Sequence[dict[str, Any]],
    *,
    idle_phases: frozenset[str] = IDLE_BASELINE_PHASES,
) -> dict[str, Any]:
    """Mean board power on true idle phase (not cooldown) within the session."""
    vals = []
    for s in samples:
        phase = str(s.get("phase") or "")
        if phase not in idle_phases:
            continue
        pw = board_power_w(s)
        if pw is not None:
            vals.append(pw)
    if len(vals) < 2:
        # Fallback: first 5 samples (often idle start)
        for s in list(samples)[:5]:
            pw = board_power_w(s)
            if pw is not None:
                vals.append(pw)
        source = "first_samples_fallback"
    else:
        source = "idle_phase_only"
    if not vals:
        return {"P_idle_baseline_w": None, "n": 0, "source": "unavailable"}
    return {
        "P_idle_baseline_w": sum(vals) / len(vals),
        "n": len(vals),
        "source": source,
        "P_idle_min_w": min(vals),
        "P_idle_max_w": max(vals),
    }


def overload_with_duration(
    times_s: Sequence[float],
    powers_w: Sequence[float],
    samples: Sequence[dict[str, Any]] | None = None,
    *,
    warn_w: float = WARN_W_DEFAULT,
    critical_w: float = CRITICAL_W_DEFAULT,
    min_duration_s: float = WARN_MIN_DURATION_S,
) -> dict[str, Any]:
    """Warn/critical only if P exceeds threshold for contiguous duration ≥ τ."""
    n = min(len(times_s), len(powers_w))
    if n < 1:
        return {
            "level": "unknown",
            "reason": "no_samples",
            "peak_w": None,
            "warn_w": warn_w,
            "critical_w": critical_w,
            "min_duration_s": min_duration_s,
            "time_above_warn_s": 0.0,
            "time_above_critical_s": 0.0,
            "longest_warn_run_s": 0.0,
            "operational": False,
            "physical_context": {},
        }

    t = [float(times_s[i]) for i in range(n)]
    p = [float(powers_w[i]) for i in range(n)]
    peak = max(p)

    def _run_time(threshold: float) -> tuple[float, float]:
        """Return (total_time_above, longest_contiguous_run)."""
        total = 0.0
        longest = 0.0
        run = 0.0
        for i in range(n - 1):
            dt = t[i + 1] - t[i]
            if p[i] >= threshold or p[i + 1] >= threshold:
                # count interval if either endpoint exceeds (conservative)
                if p[i] >= threshold and p[i + 1] >= threshold:
                    total += dt
                    run += dt
                    longest = max(longest, run)
                else:
                    # partial — count half
                    total += 0.5 * dt
                    run = 0.0
            else:
                run = 0.0
        if n == 1:
            return (0.0, 0.0)
        return total, longest

    tw, longest_w = _run_time(warn_w)
    tc, longest_c = _run_time(critical_w)

    if min_duration_s <= 0.0:
        # Instantaneous legacy mode (no hysteresis)
        if peak >= critical_w:
            level = "critical"
            reason = f"instantaneous_peak>={critical_w}W"
        elif peak >= warn_w:
            level = "warn"
            reason = f"instantaneous_peak>={warn_w}W"
        else:
            level = "ok"
            reason = "below_warn_threshold"
    elif longest_c >= min_duration_s:
        level = "critical"
        reason = f"P>={critical_w}W for>={min_duration_s}s (longest_run={longest_c:.2f}s)"
    elif longest_w >= min_duration_s:
        level = "warn"
        reason = f"P>={warn_w}W for>={min_duration_s}s (longest_run={longest_w:.2f}s)"
    elif peak >= warn_w:
        level = "ok"
        reason = (
            f"instantaneous_peak_{peak:.1f}W_below_min_duration_"
            f"{min_duration_s}s (not_warned)"
        )
    else:
        level = "ok"
        reason = "below_warn_threshold"

    # Physical context from samples overlapping high-power region
    ctx: dict[str, Any] = {
        "high_rail_power": peak >= warn_w,
        "sustained_above_warn": longest_w >= min_duration_s,
        "gpu_power_limiting": None,
        "coolant_c_max": None,
        "coolant_c_delta": None,
        "pcie_vs_8pin": None,
        "note": "Diagnostic context only; not validated against throttle events yet.",
    }
    if samples:
        coolants = [_finite(s.get("coolant_c")) for s in samples]
        coolants_f = [c for c in coolants if c is not None]
        if coolants_f:
            ctx["coolant_c_max"] = max(coolants_f)
            ctx["coolant_c_delta"] = max(coolants_f) - min(coolants_f)
        pcie_vals, pin8_vals = [], []
        gpu_vals = []
        for s in samples:
            a, b = _pcie_pin8(s)
            if a is not None:
                pcie_vals.append(a)
            if b is not None:
                pin8_vals.append(b)
            pr = s.get("P_rails") or {}
            wg = _finite(pr.get("w_gpu"))
            if wg is not None:
                gpu_vals.append(wg)
        if pcie_vals and pin8_vals:
            mean_pcie = sum(pcie_vals) / len(pcie_vals)
            mean_pin8 = sum(pin8_vals) / len(pin8_vals)
            ratio = mean_pin8 / max(mean_pcie, 1e-6)
            ctx["pcie_vs_8pin"] = {
                "mean_pcie_w": mean_pcie,
                "mean_pin8_w": mean_pin8,
                "pin8_over_pcie": ratio,
                "unusual": ratio > 8.0 or ratio < 0.5,
            }
        if gpu_vals and len(gpu_vals) >= 4:
            # crude: flat high GPU watts may indicate limit — flag for review
            late = gpu_vals[len(gpu_vals) // 2 :]
            early = gpu_vals[: len(gpu_vals) // 2]
            ctx["gpu_power_limiting"] = {
                "suspected": (
                    statistics.pstdev(late) < 3.0
                    and statistics.fmean(late) > 100.0
                    and statistics.fmean(late) >= statistics.fmean(early) * 0.95
                ),
                "gpu_mean_w": statistics.fmean(gpu_vals),
                "gpu_late_std_w": statistics.pstdev(late),
            }

    return {
        "level": level,
        "reason": reason,
        "peak_w": peak,
        "warn_w": warn_w,
        "critical_w": critical_w,
        "min_duration_s": min_duration_s,
        "time_above_warn_s": tw,
        "time_above_critical_s": tc,
        "longest_warn_run_s": longest_w,
        "longest_critical_run_s": longest_c,
        "operational": False,
        "physical_context": ctx,
    }


def validated_energy(
    samples: Sequence[dict[str, Any]],
    *,
    P_idle_baseline_w: float | None = None,
    warn_w: float = WARN_W_DEFAULT,
    critical_w: float = CRITICAL_W_DEFAULT,
    min_warn_duration_s: float = WARN_MIN_DURATION_S,
    stale_s: float = STALE_SENSOR_S,
) -> dict[str, Any]:
    """Validated E_gross / E_net with measurement-quality fields."""
    n_raw = len(samples)
    times: list[float] = []
    powers: list[float] = []
    used_samples: list[dict[str, Any]] = []
    missing = 0
    stale = 0
    for s in samples:
        age = _finite(s.get("sensor_age_s"))
        if age is not None and age > stale_s:
            stale += 1
        pw = board_power_w(s)
        mono = _finite(s.get("mono_s"))
        if pw is None or mono is None:
            missing += 1
            continue
        times.append(mono)
        powers.append(pw)
        used_samples.append(s)

    integ = integrate_energy_j(times, powers)
    E_gross = integ.get("E_j") if integ.get("ok") else None
    duration = integ.get("duration_s")
    P_mean = (sum(powers) / len(powers)) if powers else None
    P_peak = peak_power_w(powers)

    if P_idle_baseline_w is None:
        base = idle_baseline_w(samples)
        P_idle_baseline_w = base.get("P_idle_baseline_w")
        idle_meta = base
    else:
        idle_meta = {"P_idle_baseline_w": P_idle_baseline_w, "source": "provided"}

    E_net = None
    if E_gross is not None and P_idle_baseline_w is not None and duration is not None:
        E_net = E_gross - float(P_idle_baseline_w) * float(duration)

    quality = _quality_and_confidence(
        n_raw=n_raw,
        n_power=len(powers),
        n_missing_power=missing,
        n_stale=stale,
        largest_gap_s=integ.get("largest_gap_s"),
        cadence_s=integ.get("mean_cadence_s"),
        E_gross=E_gross if isinstance(E_gross, (int, float)) else None,
        P_mean=P_mean,
        duration_s=duration if isinstance(duration, (int, float)) else None,
    )
    if E_net is not None and float(E_net) < 0.0:
        quality["confidence_reasons"] = list(quality.get("confidence_reasons") or []) + [
            "negative_E_net_baseline_exceeds_action"
        ]
        if quality.get("confidence") == "valid":
            quality["confidence"] = "degraded"

    overload = overload_with_duration(
        times,
        powers,
        used_samples,
        warn_w=warn_w,
        critical_w=critical_w,
        min_duration_s=min_warn_duration_s,
    )

    return {
        "ok": quality["confidence"] != "invalid" and E_gross is not None,
        "E_gross_j": E_gross,
        "E_net_j": E_net,
        "P_mean_w": P_mean,
        "P_peak_w": P_peak,
        "duration_s": duration,
        "P_idle_baseline_w": P_idle_baseline_w,
        "idle_baseline": idle_meta,
        "quality": quality,
        "confidence": quality["confidence"],
        "overload": overload,
        "integration": integ,
        "authority": "action_cost_ledger_only",
        "enters_A_t": False,
        "enters_master_s_n": False,
        "predictor_operational": False,
    }


def _phase_segments(samples: Sequence[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Split samples into contiguous phase runs."""
    if not samples:
        return []
    segs: list[tuple[str, list[dict[str, Any]]]] = []
    cur_phase = str(samples[0].get("phase") or "unknown")
    buf: list[dict[str, Any]] = []
    for s in samples:
        ph = str(s.get("phase") or "unknown")
        if ph != cur_phase and buf:
            segs.append((cur_phase, buf))
            buf = []
            cur_phase = ph
        buf.append(s)
    if buf:
        segs.append((cur_phase, buf))
    return segs


def _condition_tags(samples: Sequence[dict[str, Any]], meta: dict[str, Any] | None) -> list[str]:
    tags: list[str] = []
    coolants = [_finite(s.get("coolant_c")) for s in samples]
    coolants_f = [c for c in coolants if c is not None]
    if coolants_f:
        mean_c = sum(coolants_f) / len(coolants_f)
        tags.append("coolant_warm" if mean_c >= 40.0 else "coolant_cold")
    wl = str((meta or {}).get("workload") or (samples[0].get("workload") if samples else ""))
    if "gpu" in wl or wl == "mixed":
        tags.append("gpu_inference_path")
    if wl in {"cpu_ramp", "cpu_gpu_switch", "coolant_eq"}:
        tags.append("cpu_load_path")
    if wl == "mixed":
        tags.append("simultaneous_cpu_gpu")
    # first vs repeated: caller may add; default unknown
    return tags


def action_record(
    *,
    action_id: str,
    action_type: str,
    workload: str,
    samples: Sequence[dict[str, Any]],
    meta: dict[str, Any] | None = None,
    P_idle_baseline_w: float | None = None,
    model: str | None = None,
    token_count: int | None = None,
    task_size: float | None = None,
    inference_params: dict[str, Any] | None = None,
    condition_tags: Sequence[str] | None = None,
) -> dict[str, Any]:
    """One bounded action cost row for the ledger."""
    meta = meta or {}
    energy = validated_energy(samples, P_idle_baseline_w=P_idle_baseline_w)
    t0 = samples[0].get("at") if samples else None
    t1 = samples[-1].get("at") if samples else None
    mono0 = _finite(samples[0].get("mono_s")) if samples else None
    mono1 = _finite(samples[-1].get("mono_s")) if samples else None
    duration = energy.get("duration_s")
    E_net = energy.get("E_net_j")
    E_gross = energy.get("E_gross_j")

    j_per_s = None
    if E_net is not None and duration and duration > 0:
        j_per_s = float(E_net) / float(duration)
    j_per_token = None
    if E_net is not None and token_count is not None and token_count > 0:
        j_per_token = float(E_net) / float(token_count)

    tags = list(condition_tags) if condition_tags is not None else _condition_tags(samples, meta)
    if model is None:
        for ev in meta.get("events") or []:
            if isinstance(ev, dict) and ev.get("model"):
                model = str(ev["model"])
                break

    return {
        "action_id": action_id,
        "action_type": action_type,
        "workload": workload,
        "t_start": t0,
        "t_end": t1,
        "mono_start_s": mono0,
        "mono_end_s": mono1,
        "model": model,
        "inference_params": inference_params or {},
        "token_count": token_count,
        "task_size": task_size,
        "task_size_note": (
            None
            if token_count is not None
            else "token_count_not_instrumented_in_capture"
        ),
        "E_gross_j": E_gross,
        "E_net_j": E_net,
        "P_mean_w": energy.get("P_mean_w"),
        "P_peak_w": energy.get("P_peak_w"),
        "J_per_second": j_per_s,
        "J_per_token": j_per_token,
        "J_per_action": E_net,
        "time_above_warn_s": (energy.get("overload") or {}).get("time_above_warn_s"),
        "overload_level": (energy.get("overload") or {}).get("level"),
        "overload_reason": (energy.get("overload") or {}).get("reason"),
        "overload_physical_context": (energy.get("overload") or {}).get("physical_context"),
        "confidence": energy.get("confidence"),
        "quality": energy.get("quality"),
        "condition_tags": tags,
        "n_samples": len(samples),
        "authority": "action_cost_ledger_only",
        "enters_A_t": False,
        "enters_master_s_n": False,
        "human_summary": _human_summary(
            action_type=action_type,
            model=model,
            token_count=token_count,
            duration=duration,
            E_net=E_net if isinstance(E_net, (int, float)) else None,
            P_peak=energy.get("P_peak_w") if isinstance(energy.get("P_peak_w"), (int, float)) else None,
            confidence=str(energy.get("confidence")),
        ),
    }


def _human_summary(
    *,
    action_type: str,
    model: str | None,
    token_count: int | None,
    duration: float | None,
    E_net: float | None,
    P_peak: float | None,
    confidence: str,
) -> str:
    parts = [action_type]
    if model:
        parts.append(f"model={model}")
    if token_count is not None:
        parts.append(f"{token_count} tokens")
    if duration is not None:
        parts.append(f"{duration:.1f}s")
    if E_net is not None:
        if E_net >= 1000:
            parts.append(f"{E_net/1000:.2f} kJ net")
        else:
            parts.append(f"{E_net:.0f} J net")
    if P_peak is not None:
        parts.append(f"{P_peak:.0f} W peak")
    parts.append(f"confidence={confidence}")
    return ", ".join(parts)


def ledger_from_session(
    samples: Sequence[dict[str, Any]],
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build per-phase action rows + session totals for one capture."""
    meta = dict(meta or {})
    workload = str(meta.get("workload") or (samples[0].get("workload") if samples else "unknown"))
    session_id = str(meta.get("session_id") or (samples[0].get("session_id") if samples else "unknown"))
    idle = idle_baseline_w(samples)
    P_idle = idle.get("P_idle_baseline_w")

    actions: list[dict[str, Any]] = []
    for i, (phase, seg) in enumerate(_phase_segments(samples)):
        actions.append(
            action_record(
                action_id=f"{session_id}::phase::{phase}::{i}",
                action_type=f"phase:{phase}",
                workload=workload,
                samples=seg,
                meta=meta,
                P_idle_baseline_w=P_idle if isinstance(P_idle, (int, float)) else None,
            )
        )

    # Active-load composite (exclude pure idle/cooldown)
    active = [s for s in samples if str(s.get("phase") or "") not in IDLE_PHASE_NAMES]
    if len(active) >= 2:
        actions.append(
            action_record(
                action_id=f"{session_id}::active_load",
                action_type="active_load",
                workload=workload,
                samples=active,
                meta=meta,
                P_idle_baseline_w=P_idle if isinstance(P_idle, (int, float)) else None,
                condition_tags=_condition_tags(samples, meta) + ["active_load_composite"],
            )
        )

    session_total = validated_energy(
        samples, P_idle_baseline_w=P_idle if isinstance(P_idle, (int, float)) else None
    )

    return {
        "ok": True,
        "session_id": session_id,
        "workload": workload,
        "idle_baseline": idle,
        "session_total": session_total,
        "actions": actions,
        "n_actions": len(actions),
        "authority": "action_cost_ledger_only",
        "enters_A_t": False,
        "enters_master_s_n": False,
        "experiment_id": "rid_electrical_action_ledger_v1",
    }


def _mean_std(vals: list[float]) -> tuple[float | None, float | None]:
    if not vals:
        return None, None
    if len(vals) == 1:
        return vals[0], 0.0
    return statistics.fmean(vals), statistics.pstdev(vals)


def cost_profiles_from_actions(
    action_rows: Sequence[dict[str, Any]],
    *,
    action_type_filter: str | None = "active_load",
) -> dict[str, Any]:
    """μ/σ of E_net and P_peak by workload (and optional tags)."""
    by_wl: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in action_rows:
        if action_type_filter and row.get("action_type") != action_type_filter:
            continue
        if row.get("confidence") == "invalid":
            continue
        if row.get("E_net_j") is None:
            continue
        by_wl[str(row.get("workload"))].append(row)

    profiles = {}
    for wl, rows in sorted(by_wl.items()):
        e_vals = [float(r["E_net_j"]) for r in rows]
        p_vals = [float(r["P_peak_w"]) for r in rows if r.get("P_peak_w") is not None]
        jps = [float(r["J_per_second"]) for r in rows if r.get("J_per_second") is not None]
        mu_e, sig_e = _mean_std(e_vals)
        mu_p, sig_p = _mean_std(p_vals)
        mu_jps, sig_jps = _mean_std(jps)
        # Stability: relative σ
        stable = None
        if mu_e is not None and abs(mu_e) > 1.0 and sig_e is not None:
            cv = sig_e / abs(mu_e)
            stable = cv <= 0.25
        profiles[wl] = {
            "n": len(rows),
            "mu_E_net_j": mu_e,
            "sigma_E_net_j": sig_e,
            "mu_P_peak_w": mu_p,
            "sigma_P_peak_w": sig_p,
            "mu_J_per_second": mu_jps,
            "sigma_J_per_second": sig_jps,
            "cv_E_net": (sig_e / abs(mu_e)) if mu_e and sig_e is not None and abs(mu_e) > 1 else None,
            "repeatable_signature": stable,
            "overload_levels": {
                k: sum(1 for r in rows if r.get("overload_level") == k)
                for k in sorted({str(r.get("overload_level")) for r in rows})
            },
            "confidence_mix": {
                k: sum(1 for r in rows if r.get("confidence") == k)
                for k in sorted({str(r.get("confidence")) for r in rows})
            },
            "example_summaries": [r.get("human_summary") for r in rows[:3]],
        }

    n_stable = sum(1 for p in profiles.values() if p.get("repeatable_signature") is True)
    return {
        "ok": True,
        "action_type_filter": action_type_filter,
        "profiles": profiles,
        "n_workloads": len(profiles),
        "n_repeatable_signatures": n_stable,
        "note": (
            "Profiles from ledger actions only. Prediction of E/P comes later "
            "after signatures are stable. Not Master/routing."
        ),
        "authority": "action_cost_ledger_only",
    }


# --- Back-compat thin wrappers for outcomes_observe ---


def overload_risk(
    powers_w: Sequence[float],
    *,
    warn_w: float,
    critical_w: float,
) -> dict[str, Any]:
    """Legacy instantaneous API — prefer overload_with_duration."""
    times = list(range(len(powers_w)))
    return overload_with_duration(
        [float(t) for t in times],
        list(powers_w),
        warn_w=warn_w,
        critical_w=critical_w,
        min_duration_s=0.0,  # preserve old instantaneous behavior when τ=0
    )


def outcomes_from_samples(
    samples: Sequence[dict[str, Any]],
    *,
    warn_w: float = WARN_W_DEFAULT,
    critical_w: float = CRITICAL_W_DEFAULT,
) -> dict[str, Any]:
    """Back-compat: session-level validated energy + duration-gated overload."""
    v = validated_energy(
        samples,
        warn_w=warn_w,
        critical_w=critical_w,
        min_warn_duration_s=WARN_MIN_DURATION_S,
    )
    return {
        "ok": v.get("ok"),
        "target": "direct_electrical_outcomes_not_master_s_n",
        "E_action_j": v.get("E_gross_j"),
        "E_gross_j": v.get("E_gross_j"),
        "E_net_j": v.get("E_net_j"),
        "duration_s": v.get("duration_s"),
        "P_peak_w": v.get("P_peak_w"),
        "P_mean_w": v.get("P_mean_w"),
        "overload_risk": v.get("overload"),
        "quality": v.get("quality"),
        "confidence": v.get("confidence"),
        "n_power_samples": (v.get("quality") or {}).get("n_power_samples"),
        "n_missing_power": (v.get("quality") or {}).get("n_missing_power"),
        "integration": v.get("integration"),
        "authority": "action_cost_ledger_only",
        "enters_A_t": False,
        "enters_master_s_n": False,
        "predictor_operational": False,
    }
