#!/usr/bin/env python3
"""Session-held-out electrical info-gain evaluation (whole sessions, not row splits).

Primary metric:
  Delta_info = MAE_baseline - MAE_baseline+electrical
on held-out *sessions*. Secondary: lead time, calibration, false warnings,
by-workload breakdown, overhead.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_admission import MAE_IMPROVE_MIN, MASTER_VAR_MIN
from lib.rid_electrical_capture import load_session_meta, load_session_samples

SESSIONS_ROOT = AUTO_ARTIFACTS / "rid_electrical" / "sessions"
FALSE_WARNING_CEILING = 0.25  # fraction; MAE gain with excess FAs is not clean
WARN_DROP = 0.05  # Master S_n drop threshold for "transition warning"
# Decisive evidence requires adequate Master dynamics (stricter than tiny epsilon).
DECISIVE_MASTER_VAR_MIN = 1e-4


def list_session_dirs(root: Path | None = None) -> list[Path]:
    base = root or SESSIONS_ROOT
    if not base.is_dir():
        return []
    dirs = [
        p
        for p in base.iterdir()
        if p.is_dir()
        and (p / "samples.jsonl").is_file()
        and (p / "session_meta.json").is_file()
    ]
    return sorted(dirs, key=lambda p: p.name)


def session_series(session_dir: Path) -> dict[str, Any]:
    samples = load_session_samples(session_dir)
    meta = load_session_meta(session_dir)
    masters = [float(s["master_s_n"]) for s in samples if s.get("master_s_n") is not None]
    s_el = [float(s["S_electrical"]) for s in samples if s.get("S_electrical") is not None]
    overhead = [float(s.get("collect_overhead_ms") or 0.0) for s in samples]
    var = None
    if len(masters) >= 2:
        mu = sum(masters) / len(masters)
        var = sum((x - mu) ** 2 for x in masters) / len(masters)
    return {
        "session_id": meta.get("session_id") or session_dir.name,
        "workload": meta.get("workload") or samples[0].get("workload") if samples else None,
        "meta": meta,
        "samples": samples,
        "n": len(samples),
        "master_series": masters,
        "s_electrical_series": s_el,
        "master_var": var,
        "dynamic": var is not None and var >= MASTER_VAR_MIN,
        "decisive_dynamic": var is not None and var >= DECISIVE_MASTER_VAR_MIN,
        "smoke": bool(meta.get("smoke")),
        "mean_overhead_ms": (sum(overhead) / len(overhead)) if overhead else None,
    }


def qualify_for_prediction(session: dict[str, Any]) -> bool:
    """Session must be non-smoke with adequate Master S_n variance."""
    meta = session.get("meta") or {}
    if meta.get("incomplete"):
        return False
    if session.get("smoke") or meta.get("smoke"):
        return False
    return bool(session.get("decisive_dynamic"))


def list_decisive_sessions(root: Path | None = None) -> list[dict[str, Any]]:
    """Full-length (non-smoke, complete) sessions only, for decisive Δ_info evidence."""
    out = []
    for d in list_session_dirs(root):
        s = session_series(d)
        meta = s.get("meta") or {}
        if s.get("smoke") or meta.get("incomplete"):
            continue
        out.append(s)
    return out


def _mae(pred: Sequence[float], actual: Sequence[float]) -> float | None:
    n = min(len(pred), len(actual))
    if n < 1:
        return None
    return sum(abs(float(pred[i]) - float(actual[i])) for i in range(n)) / n


def _fit_blend(
    masters: Sequence[float],
    feat: Sequence[float],
    targets: Sequence[float],
) -> tuple[float, float]:
    n = min(len(masters), len(feat), len(targets))
    if n < 3:
        return 1.0, 0.0
    s_mm = s_mf = s_ff = s_mt = s_ft = 0.0
    for i in range(n):
        m, f, t = float(masters[i]), float(feat[i]), float(targets[i])
        s_mm += m * m
        s_mf += m * f
        s_ff += f * f
        s_mt += m * t
        s_ft += f * t
    det = s_mm * s_ff - s_mf * s_mf
    if abs(det) < 1e-12:
        return 1.0, 0.0
    a = (s_ff * s_mt - s_mf * s_ft) / det
    b = (s_mm * s_ft - s_mf * s_mt) / det
    return a, b


def _one_step_pairs(samples: list[dict[str, Any]], feat_key: str) -> tuple[list[float], list[float], list[float]]:
    ms, fs, tg = [], [], []
    for i in range(len(samples) - 1):
        a, b = samples[i], samples[i + 1]
        if a.get("master_s_n") is None or b.get("master_s_n") is None:
            continue
        feat = _feature_value(a, feat_key)
        if feat is None:
            continue
        ms.append(float(a["master_s_n"]))
        fs.append(float(feat))
        tg.append(float(b["master_s_n"]))
    return ms, fs, tg


def _feature_value(sample: dict[str, Any], key: str) -> float | None:
    if key == "none":
        return 0.0
    if key == "S_electrical":
        v = sample.get("S_electrical")
        return None if v is None else float(v)
    if key == "P":
        p = sample.get("P_rails") or {}
        vals = [p.get("w_cpu"), p.get("w_gpu")]
        nums = [float(x) for x in vals if x is not None]
        return None if not nums else sum(nums) / len(nums)
    if key == "P_V":
        p = sample.get("P_rails") or {}
        v = sample.get("V_rails") or {}
        vals = [p.get("w_cpu"), p.get("w_gpu"), v.get("v_cpu"), v.get("v_gpu")]
        nums = [float(x) for x in vals if x is not None]
        return None if not nums else sum(nums) / len(nums)
    if key == "P_V_I":
        p = sample.get("P_rails") or {}
        v = sample.get("V_rails") or {}
        i = sample.get("I_derived") or {}
        vals = [
            p.get("w_cpu"),
            p.get("w_gpu"),
            v.get("v_cpu"),
            v.get("v_gpu"),
            i.get("i_cpu"),
            i.get("i_gpu"),
        ]
        nums = [float(x) for x in vals if x is not None]
        return None if not nums else sum(nums) / len(nums)
    return None


def evaluate_feature_on_holdout(
    train_sessions: list[dict[str, Any]],
    test_sessions: list[dict[str, Any]],
    feat_key: str,
) -> dict[str, Any]:
    """Fit on train sessions (concatenated), score one-step MAE on test sessions."""
    train_ms: list[float] = []
    train_fs: list[float] = []
    train_tg: list[float] = []
    for s in train_sessions:
        ms, fs, tg = _one_step_pairs(s["samples"], feat_key)
        train_ms.extend(ms)
        train_fs.extend(fs)
        train_tg.extend(tg)

    if feat_key == "none":
        a, b = 1.0, 0.0
    else:
        a, b = _fit_blend(train_ms, train_fs, train_tg)

    base_errs: list[float] = []
    pilot_errs: list[float] = []
    by_workload: dict[str, dict[str, list[float]]] = {}

    for s in test_sessions:
        ms, fs, tg = _one_step_pairs(s["samples"], feat_key if feat_key != "none" else "S_electrical")
        # For baseline persistence we only need ms→tg; for none feature use zeros
        if feat_key == "none":
            ms2, _, tg2 = _one_step_pairs(s["samples"], "S_electrical")
            if not ms2:
                # still try master-only pairs
                samples = s["samples"]
                ms2, tg2 = [], []
                for i in range(len(samples) - 1):
                    if samples[i].get("master_s_n") is None or samples[i + 1].get("master_s_n") is None:
                        continue
                    ms2.append(float(samples[i]["master_s_n"]))
                    tg2.append(float(samples[i + 1]["master_s_n"]))
                fs2 = [0.0] * len(ms2)
            else:
                fs2 = [0.0] * len(ms2)
            ms, fs, tg = ms2, fs2, tg2
        if not tg:
            continue
        wl = str(s.get("workload") or "unknown")
        bucket = by_workload.setdefault(wl, {"base": [], "pilot": []})
        for m, f, t in zip(ms, fs, tg):
            base = abs(m - t)  # persistence
            pilot = abs((a * m + b * f) - t)
            base_errs.append(base)
            pilot_errs.append(pilot)
            bucket["base"].append(base)
            bucket["pilot"].append(pilot)

    base_mae = (sum(base_errs) / len(base_errs)) if base_errs else None
    pilot_mae = (sum(pilot_errs) / len(pilot_errs)) if pilot_errs else None
    delta = None
    if base_mae is not None and pilot_mae is not None:
        delta = float(base_mae) - float(pilot_mae)

    wl_summary = {}
    for wl, b in by_workload.items():
        bm = sum(b["base"]) / len(b["base"]) if b["base"] else None
        pm = sum(b["pilot"]) / len(b["pilot"]) if b["pilot"] else None
        wl_summary[wl] = {
            "baseline_mae": bm,
            "pilot_mae": pm,
            "delta_info": (None if bm is None or pm is None else bm - pm),
            "n": len(b["base"]),
        }

    return {
        "feature": feat_key,
        "fit_n": len(train_tg),
        "test_n": len(base_errs),
        "blend_a": a,
        "blend_b": b,
        "baseline_mae": base_mae,
        "pilot_mae": pilot_mae,
        "delta_info": delta,
        "by_workload": wl_summary,
    }


def secondary_metrics(test_sessions: list[dict[str, Any]], feat_key: str = "S_electrical") -> dict[str, Any]:
    """Transition lead time, calibration, false warning rate, overhead."""
    leads: list[float] = []
    false_warn = 0
    true_warn = 0
    warn_events = 0
    calib_err: list[float] = []
    overhead: list[float] = []

    for s in test_sessions:
        samples = s["samples"]
        for x in samples:
            if x.get("collect_overhead_ms") is not None:
                overhead.append(float(x["collect_overhead_ms"]))
        # Detect Master drops and whether electrical dipped earlier
        for i in range(1, len(samples)):
            m0 = samples[i - 1].get("master_s_n")
            m1 = samples[i].get("master_s_n")
            if m0 is None or m1 is None:
                continue
            drop = float(m0) - float(m1)
            if drop >= WARN_DROP:
                # look back up to 5 samples for S_electrical drop
                lead = None
                for k in range(1, min(6, i + 1)):
                    e0 = samples[i - k].get(feat_key if feat_key == "S_electrical" else "S_electrical")
                    e1 = samples[i - k + 1].get("S_electrical") if i - k + 1 < len(samples) else None
                    # simpler: electrical lower than prior mean
                    e_now = samples[i - k].get("S_electrical")
                    if e_now is not None and float(e_now) < 0.3:
                        lead = float(k) * float(samples[i].get("cadence_s") or 1.0)
                        break
                if lead is not None:
                    leads.append(lead)
                    true_warn += 1
                warn_events += 1
            # false warning: electrical low but master not dropping next
            e = samples[i - 1].get("S_electrical")
            if e is not None and float(e) < 0.2 and drop < WARN_DROP / 2:
                false_warn += 1
            # calibration: predicted next master via persistence vs actual
            calib_err.append(abs(float(m0) - float(m1)))

    fa_rate = None
    denom = false_warn + true_warn
    if denom > 0:
        fa_rate = false_warn / denom
    return {
        "transition_warning_lead_time_s_mean": (sum(leads) / len(leads)) if leads else None,
        "transition_warnings_detected": true_warn,
        "false_warning_count": false_warn,
        "false_warning_rate": fa_rate,
        "calibration_mae_persistence": (sum(calib_err) / len(calib_err)) if calib_err else None,
        "mean_collect_overhead_ms": (sum(overhead) / len(overhead)) if overhead else None,
        "false_warning_ceiling": FALSE_WARNING_CEILING,
    }


def split_train_test_sessions(
    series: list[dict[str, Any]],
    *,
    min_test: int = 1,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Chronological whole-session split: earlier = train, later = test."""
    if len(series) < 2:
        return series[:0], series
    # Prefer leaving at least one dynamic session in test when possible
    cut = max(1, len(series) - max(min_test, len(series) // 3))
    if cut >= len(series):
        cut = len(series) - 1
    return series[:cut], series[cut:]


def clean_improvement(delta_info: float | None, secondary: dict[str, Any]) -> bool:
    if delta_info is None or delta_info < MAE_IMPROVE_MIN:
        return False
    fa = secondary.get("false_warning_rate")
    if fa is not None and float(fa) > FALSE_WARNING_CEILING:
        return False
    return True
