#!/usr/bin/env python3
"""Shadow A/B info-gain gate for electrical vs Master — no authority write.

Δ_info = performance(Master + shadow electrical) − performance(Master baseline)

Lane advancement requires positive Δ_info across multiple independent,
sufficiently dynamic unseen windows under predefined acceptance criteria
(lib/rid_electrical_admission.py). One isolated strong window does not advance
the lane; it remains measured in shadow. Never mutates Master.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_shadow_ab.py
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_shadow_ab.py --samples 30 --sleep 1.0
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.master_rid import MASTER_RID_PATH, load_master_rid  # noqa: E402
from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical import active_set_master, ratio  # noqa: E402
from lib.rid_electrical_admission import (  # noqa: E402
    MAE_IMPROVE_MIN as CRIT_MAE,
    MASTER_VAR_MIN,
    MIN_PASSING_WINDOWS,
    MIN_WINDOW_SEPARATION_S,
    archive_window_report,
    evaluate_multiwindow,
    write_multiwindow_report,
)

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
EXPERIMENT_ID = "rid_electrical_shadow_ab_v2"
FLAG = "rid_electrical_observe_v1"
MIN_VALID = 10
CORR_DEPENDENCE_THRESH = 0.92
MAE_IMPROVE_MIN = CRIT_MAE


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 3:
        return None
    x = xs[:n]
    y = ys[:n]
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    denx = math.sqrt(sum((a - mx) ** 2 for a in x))
    deny = math.sqrt(sum((b - my) ** 2 for b in y))
    if denx <= 1e-12 or deny <= 1e-12:
        return None
    return num / (denx * deny)


def _mae(pred: list[float], actual: list[float]) -> float | None:
    n = min(len(pred), len(actual))
    if n < 1:
        return None
    return sum(abs(pred[i] - actual[i]) for i in range(n)) / n


def _fit_blend(masters: list[float], elec: list[float], targets: list[float]) -> tuple[float, float]:
    """Least-squares: target ≈ a*master + b*electrical (no intercept)."""
    n = min(len(masters), len(elec), len(targets))
    if n < 3:
        return 1.0, 0.0
    s_mm = s_me = s_ee = s_mt = s_et = 0.0
    for i in range(n):
        m, e, t = masters[i], elec[i], targets[i]
        s_mm += m * m
        s_me += m * e
        s_ee += e * e
        s_mt += m * t
        s_et += e * t
    det = s_mm * s_ee - s_me * s_me
    if abs(det) < 1e-12:
        return 1.0, 0.0
    a = (s_ee * s_mt - s_me * s_et) / det
    b = (s_mm * s_et - s_me * s_mt) / det
    return a, b


def _observe_live() -> dict[str, Any]:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "rid_electrical_observe",
        FOUNDATION / "scripts" / "rid_electrical_observe.py",
    )
    if spec is None or spec.loader is None:
        return {}
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.observe_once()


def run(*, samples: int = 30, sleep_s: float = 1.0) -> dict[str, Any]:
    master_text_before = (
        MASTER_RID_PATH.read_text(encoding="utf-8") if MASTER_RID_PATH.is_file() else None
    )
    rows: list[dict[str, Any]] = []
    t0 = time.perf_counter()

    for i in range(max(1, int(samples))):
        obs = _observe_live()
        meters = obs.get("meters") or {}
        elec = obs.get("electrical") or {}
        m = load_master_rid()
        s_map: dict[str, float] = {}
        if m is not None:
            s_map = {k: float(v.s_n) for k, v in m.subsystems.items() if v.available}

        baseline_geom = active_set_master(s_map, list(s_map.keys())) if s_map else None
        pilot_geom = None
        geom_delta = None
        s_el = elec.get("s_electrical")
        available = bool(elec.get("available"))
        if available and s_el is not None and s_map:
            pilot_map = dict(s_map)
            pilot_map["electrical"] = float(s_el)
            pilot_geom = active_set_master(pilot_map, list(pilot_map.keys()))
            geom_delta = float(pilot_geom) - float(baseline_geom)

        w_cpu, w_gpu = meters.get("w_cpu"), meters.get("w_gpu")
        s_w_only = None
        if w_cpu is not None and w_gpu is not None:
            s_w_only = float(ratio(float(w_cpu), float(w_gpu), required=True))

        rows.append(
            {
                "i": i,
                "at": _utc(),
                "master_s_n": None if m is None else float(m.master_s_n),
                "master_status": None if m is None else m.status,
                "master_subsystems": sorted(s_map.keys()),
                "s_electrical": s_el,
                "electrical_available": available,
                "i_gpu": meters.get("i_gpu"),
                "i_gpu_origin": (meters.get("origins") or {}).get("i_gpu"),
                "i_gpu_independent": (meters.get("independent_axes") or {}).get("i_gpu"),
                "w_cpu": w_cpu,
                "w_gpu": w_gpu,
                "s_w_only_proxy": s_w_only,
                "shadow_baseline_geom": baseline_geom,
                "shadow_pilot_geom": pilot_geom,
                "shadow_geom_delta": geom_delta,
            }
        )
        if i + 1 < samples:
            time.sleep(float(sleep_s))

    elapsed = time.perf_counter() - t0
    master_text_after = (
        MASTER_RID_PATH.read_text(encoding="utf-8") if MASTER_RID_PATH.is_file() else None
    )
    master_after = load_master_rid()

    useful = [
        r
        for r in rows
        if r.get("electrical_available")
        and r.get("s_electrical") is not None
        and r.get("master_s_n") is not None
        and r.get("shadow_geom_delta") is not None
    ]

    origins = {r.get("i_gpu_origin") for r in useful if r.get("i_gpu_origin")}
    ohm_derived = "software_ohm_from_measured_hwinfo_rails" in origins
    any_independent_i = any(r.get("i_gpu_independent") is True for r in useful)

    s_el_series = [float(r["s_electrical"]) for r in useful]
    master_series = [float(r["master_s_n"]) for r in useful]
    w_proxy = [float(r["s_w_only_proxy"]) for r in useful if r.get("s_w_only_proxy") is not None]
    s_el_for_w = [
        float(r["s_electrical"]) for r in useful if r.get("s_w_only_proxy") is not None
    ]
    corr_master = _pearson(s_el_series, master_series)
    corr_w = _pearson(s_el_for_w, w_proxy) if len(w_proxy) >= 3 else None

    pred_block: dict[str, Any] = {
        "metric": "one_step_master_s_n_mae",
        "baseline_mae": None,
        "pilot_mae": None,
        "delta_info": None,
        "fit_n": 0,
        "test_n": 0,
        "blend_a": None,
        "blend_b": None,
    }
    if len(useful) >= MIN_VALID:
        split = max(3, int(len(useful) * 0.6))
        train = useful[:split]
        test = useful[split:]
        if len(test) >= 2:

            def pairs(block: list[dict[str, Any]]) -> tuple[list[float], list[float], list[float]]:
                ms, es, tg = [], [], []
                for j in range(len(block) - 1):
                    ms.append(float(block[j]["master_s_n"]))
                    es.append(float(block[j]["s_electrical"]))
                    tg.append(float(block[j + 1]["master_s_n"]))
                return ms, es, tg

            tr_m, tr_e, tr_t = pairs(train)
            te_m, te_e, te_t = pairs(test)
            base_mae = _mae(list(te_m), te_t)
            a, b = _fit_blend(tr_m, tr_e, tr_t)
            pilot_mae = _mae([a * m + b * e for m, e in zip(te_m, te_e)], te_t)
            delta_info = None
            if base_mae is not None and pilot_mae is not None:
                delta_info = float(base_mae) - float(pilot_mae)
            pred_block.update(
                {
                    "baseline_mae": base_mae,
                    "pilot_mae": pilot_mae,
                    "delta_info": delta_info,
                    "fit_n": len(tr_t),
                    "test_n": len(te_t),
                    "blend_a": a,
                    "blend_b": b,
                }
            )

    geom_deltas = [float(r["shadow_geom_delta"]) for r in useful]
    geom_delta_mean = (sum(geom_deltas) / len(geom_deltas)) if geom_deltas else None

    master_var = None
    if len(master_series) >= 2:
        mu = sum(master_series) / len(master_series)
        master_var = sum((x - mu) ** 2 for x in master_series) / len(master_series)

    di = pred_block.get("delta_info")
    positive_info = di is not None and float(di) >= MAE_IMPROVE_MIN
    negative_or_flat_info = di is not None and float(di) < MAE_IMPROVE_MIN
    dynamic_window = master_var is not None and master_var >= MASTER_VAR_MIN

    # Single-window verdict — never advances lane by itself.
    if len(useful) < MIN_VALID:
        verdict = "INCONCLUSIVE"
        reason = "insufficient_valid_shadow_samples"
    elif not dynamic_window:
        verdict = "INCONCLUSIVE_LOW_SIGNAL"
        reason = (
            "master_s_n_flat_in_window;"
            "lane_stays_measured_in_shadow;"
            "rerun_on_unseen_dynamic_periods"
        )
    elif ohm_derived and corr_w is not None and abs(corr_w) >= CORR_DEPENDENCE_THRESH:
        if not positive_info:
            verdict = "INCONCLUSIVE_CHANNEL_DEPENDENCE"
            reason = (
                "i_gpu_ohm_derived_redundant_with_power_proxy;"
                "lane_stays_measured_in_shadow"
            )
        else:
            verdict = "SHADOW_WINDOW_PASS"
            reason = (
                "positive_delta_info_one_window;"
                "isolated_window_does_not_advance_lane;"
                "multiwindow_criteria_required"
            )
    elif positive_info:
        verdict = "SHADOW_WINDOW_PASS"
        reason = (
            "positive_delta_info_one_window;"
            "isolated_window_does_not_advance_lane;"
            "multiwindow_criteria_required"
        )
    elif negative_or_flat_info or geom_delta_mean is not None:
        verdict = "SHADOW_ONLY"
        reason = (
            "flat_or_inconsistent_or_geom_only;"
            "lane_stays_measured_in_shadow;"
            "geom_reweight_diagnostic_only"
        )
    else:
        verdict = "INCONCLUSIVE"
        reason = "no_usable_delta_info_or_geom"

    report: dict[str, Any] = {
        "ok": True,
        "experiment_id": EXPERIMENT_ID,
        "flag": FLAG,
        "at": _utc(),
        "authority": "shadow_only_no_master_write",
        "lifecycle": "measured_in_shadow",
        "verdict": verdict,
        "reason": reason,
        "admission": {
            "granted": False,
            "electrical_in_A_t": False,
            "supports_admission_review": False,
            "lane_advancement_eligible": False,
            "rule": (
                "Lane advances only after positive Delta_info across multiple "
                "independent, sufficiently dynamic unseen windows under "
                "predefined acceptance criteria. Until then it remains "
                "measured in shadow, regardless of how strong one isolated "
                "result looks. Geom reweight is diagnostic only. Never auto-grant."
            ),
        },
        "contract": {
            "i_gpu_formula": "I_GPU = P_PCIe/V_PCIe + P_8pin/V_8pin",
            "i_gpu_stamp": "software_ohm_from_measured_hwinfo_rails",
            "derived_not_independent": True,
            "delta_info": (
                "performance(Master+shadow electrical) - performance(Master baseline)"
            ),
            "performance_metric": "one_step_master_s_n_mae_on_held_out_tail",
            "geom_reweight_is_evidence_of_info_gain": False,
            "isolated_strong_window_advances_lane": False,
            "multiwindow_acceptance": {
                "min_passing_windows": MIN_PASSING_WINDOWS,
                "mae_improve_min": MAE_IMPROVE_MIN,
                "master_var_min": MASTER_VAR_MIN,
                "min_window_separation_s": MIN_WINDOW_SEPARATION_S,
            },
        },
        "window": {
            "samples_requested": samples,
            "samples_collected": len(rows),
            "valid_shadow_rows": len(useful),
            "min_valid_required": MIN_VALID,
            "duration_s": round(elapsed, 3),
            "sleep_s": sleep_s,
            "dynamic_master": dynamic_window,
        },
        "dependence": {
            "ohm_derived_i_gpu": ohm_derived,
            "any_independent_i_gpu": any_independent_i,
            "origins_seen": sorted(o for o in origins if o),
            "corr_s_electrical_vs_master_s_n": corr_master,
            "corr_s_electrical_vs_w_only_proxy": corr_w,
            "corr_dependence_threshold": CORR_DEPENDENCE_THRESH,
            "master_s_n_variance": master_var,
        },
        "delta_info": pred_block,
        "geom_reweight": {
            "name": "active_set_geom Master vs Master+electrical",
            "delta_mean": geom_delta_mean,
            "delta_min": min(geom_deltas) if geom_deltas else None,
            "delta_max": max(geom_deltas) if geom_deltas else None,
            "is_info_gain_evidence": False,
            "note": (
                "Geometric reweighting remains diagnostic, not evidence of "
                "information gain."
            ),
        },
        "baseline": {
            "name": "master_as_today",
            "n": len(rows),
            "performance": "one_step_persistence_mae",
            "mae": pred_block["baseline_mae"],
        },
        "pilot": {
            "name": "master_plus_electrical_shadow",
            "n_valid": len(useful),
            "performance": "one_step_blend_mae",
            "mae": pred_block["pilot_mae"],
        },
        "deltas": {
            "delta_info_baseline_mae_minus_pilot_mae": pred_block["delta_info"],
            "geom_pilot_minus_baseline_mean": geom_delta_mean,
        },
        "runtime_health": {
            "master_disk_mutated": master_text_before != master_text_after,
            "master_s_n_after": None if master_after is None else master_after.master_s_n,
            "electrical_in_master_subsystems": (
                False if master_after is None else ("electrical" in master_after.subsystems)
            ),
            "errors": 0,
            "stalls": 0,
        },
        "rows": rows,
        "note": (
            "One isolated strong window does not advance the lane. "
            "Multi-window gate must see positive Delta_info across independent "
            "dynamic windows. Geom reweight is never evidence."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jpath = OUT_DIR / f"ab-report-{EXPERIMENT_ID}.json"
    mpath = OUT_DIR / f"ab-report-{EXPERIMENT_ID}.md"
    report["artifact_json"] = str(jpath).replace("\\", "/")
    report["artifact_md"] = str(mpath).replace("\\", "/")

    archive_path = archive_window_report(report)
    multi = write_multiwindow_report(evaluate_multiwindow())
    report["admission"]["supports_admission_review"] = bool(multi["supports_admission_review"])
    report["admission"]["lane_advancement_eligible"] = bool(multi["lane_advancement_eligible"])
    report["admission"]["multiwindow"] = {
        "passing_independent_n": multi["passing_independent_n"],
        "min_passing_windows": multi["criteria"]["min_passing_windows"],
        "archive_n": multi["archive_n"],
        "archive_path": str(archive_path).replace("\\", "/"),
        "artifact": multi.get("latest"),
    }
    # Lifecycle stays measured_in_shadow even if multi-window eligible (review ≠ grant).
    report["lifecycle"] = "measured_in_shadow"

    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = "\n".join(
        [
            f"# A/B report — {EXPERIMENT_ID}",
            "",
            "- **Lifecycle:** measured in shadow",
            f"- **Verdict:** {verdict}",
            f"- **Reason:** {reason}",
            (
                "- **Admission:** withheld; "
                f"lane_advancement_eligible="
                f"{report['admission']['lane_advancement_eligible']}; "
                f"supports_review={report['admission']['supports_admission_review']}"
            ),
            (
                "- **Multi-window:** "
                f"{report['admission']['multiwindow']['passing_independent_n']}/"
                f"{report['admission']['multiwindow']['min_passing_windows']} "
                "independent passing windows"
            ),
            (
                f"- **Window:** {samples} samples / {elapsed:.2f}s / "
                f"valid={len(useful)} / dynamic_master={dynamic_window}"
            ),
            f"- **Delta_info:** {di}",
            f"- **Geom reweight (diagnostic only):** {geom_delta_mean}",
            f"- **Master disk mutated:** {report['runtime_health']['master_disk_mutated']}",
            "",
            "Lane advances only after positive information gain across multiple "
            "independent, sufficiently dynamic unseen windows. One isolated "
            "strong result does not advance the lane.",
            "",
        ]
    )
    mpath.write_text(md, encoding="utf-8")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--samples", type=int, default=30, help="Shadow samples (default 30)")
    p.add_argument("--sleep", type=float, default=1.0, help="Seconds between samples")
    args = p.parse_args()
    out = run(samples=args.samples, sleep_s=args.sleep)
    slim = {k: v for k, v in out.items() if k != "rows"}
    slim["rows_n"] = len(out.get("rows") or [])
    print(json.dumps(slim, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
