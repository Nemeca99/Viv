#!/usr/bin/env python3
"""Evaluate live-shadow campaign: global + per-stratum gates + registry checks."""
from __future__ import annotations

import math
import statistics
from typing import Any, Sequence

from lib.rid_electrical_v2_uncertainty import STRATA, classify_strata

GATE_MEDIAN_EPS = 0.15
GATE_REL_MAE = 0.15
GATE_BIAS_RATIO = 0.50
GATE_SPEARMAN_ERR_GROWTH = 0.40
GATE_V1_DEGRADATION = 1.25
MIN_STRATUM_N = 10
MIN_TOTAL_N = 50

# Map strata → approval component ids
STRATUM_TO_COMPONENT = {
    "cold_load": "load",
    "warm_resident": "warm_prompt_eval",
    "prompt_short": "prompt_eval",
    "prompt_long": "prompt_eval",
    "eval_short": "prompt_eval",
    "eval_long": "prompt_eval",
    "tail_5s": "tail_5",
    "tail_10s": "tail_10",
    "tail_20s": "tail_20",
}


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 5 or len(ys) != n:
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = 0.5 * (i + j) + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    denx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    deny = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    if denx < 1e-12 or deny < 1e-12:
        return None
    return num / (denx * deny)


def summarize_residuals(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    abs_err = []
    eps = []
    resid = []
    meas = []
    for r in rows:
        e_meas = r.get("measured_energy")
        e_hat = r.get("v2_prediction")
        if e_meas is None or e_hat is None:
            continue
        a = abs(float(e_meas) - float(e_hat))
        m = float(e_meas)
        abs_err.append(a)
        resid.append(float(e_meas) - float(e_hat))
        meas.append(m)
        eps.append(a / (abs(m) if abs(m) > 1e-9 else 1e-9))
    if not abs_err:
        return {"n": 0}
    mae = statistics.fmean(abs_err)
    mu_r = statistics.fmean(resid)
    med_r = statistics.median(resid)
    return {
        "n": len(abs_err),
        "mae_j": mae,
        "rmse_j": math.sqrt(statistics.fmean([e * e for e in abs_err])),
        "rel_mae": statistics.fmean(eps),
        "median_eps": statistics.median(eps),
        "mean_residual_j": mu_r,
        "median_residual_j": med_r,
        # Robust bias: median residual (mean is outlier-dominated on long tails)
        "bias_ratio": abs(med_r) / mae if mae > 1e-12 else None,
    }


def stratum_pass(summary: dict[str, Any]) -> bool:
    if summary.get("n", 0) < MIN_STRATUM_N:
        return False
    return (
        summary.get("median_eps") is not None
        and summary["median_eps"] <= GATE_MEDIAN_EPS
        and summary.get("rel_mae") is not None
        and summary["rel_mae"] <= GATE_REL_MAE
        and summary.get("bias_ratio") is not None
        and summary["bias_ratio"] <= GATE_BIAS_RATIO
    )


def evaluate_live_shadow(actions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    global_sum = summarize_residuals(actions)
    by_stratum: dict[str, Any] = {}
    for s in STRATA:
        if s == "combined":
            continue
        subset = []
        for a in actions:
            labels = a.get("strata") or classify_strata(a)
            if s in labels:
                subset.append(a)
        by_stratum[s] = {
            "summary": summarize_residuals(subset),
            "pass": stratum_pass(summarize_residuals(subset)),
        }

    # Error growth on warm stratum
    warm = [
        a
        for a in actions
        if "warm_resident" in (a.get("strata") or classify_strata(a))
        and a.get("t_eval_s") is not None
        and a.get("v2_prediction") is not None
        and a.get("measured_energy") is not None
    ]
    te_vals = [float(a["t_eval_s"]) for a in warm]
    err_vals = [
        abs(float(a["measured_energy"]) - float(a["v2_prediction"])) for a in warm
    ]
    rho = _spearman(te_vals, err_vals)
    growth_ok = rho is None or rho <= GATE_SPEARMAN_ERR_GROWTH

    # V1 non-degradation on V1-domain rows (registry selected V1)
    v1_rows = [
        a
        for a in actions
        if a.get("registry_selected_predictor") == "V1"
        and a.get("v1_prediction") is not None
        and a.get("measured_E_net_j") is not None
    ]
    # Also compute standalone V1 MAE on same rows
    v1_reg_errs = []
    v1_solo_errs = []
    for a in v1_rows:
        meas = float(a["measured_E_net_j"])
        v1p = float(a["v1_prediction"])
        v1_solo_errs.append(abs(meas - v1p))
        # registry predicted for V1 equals v1_prediction
        reg_p = a.get("registry_predicted_E_j")
        if reg_p is None:
            reg_p = v1p
        v1_reg_errs.append(abs(meas - float(reg_p)))
    v1_ok = True
    v1_mae_reg = statistics.fmean(v1_reg_errs) if v1_reg_errs else None
    v1_mae_solo = statistics.fmean(v1_solo_errs) if v1_solo_errs else None
    if v1_mae_reg is not None and v1_mae_solo is not None and v1_mae_solo > 1e-9:
        v1_ok = v1_mae_reg <= GATE_V1_DEGRADATION * v1_mae_solo

    global_ok = (
        global_sum.get("n", 0) >= MIN_TOTAL_N
        and global_sum.get("median_eps") is not None
        and global_sum["median_eps"] <= GATE_MEDIAN_EPS
        and global_sum.get("rel_mae") is not None
        and global_sum["rel_mae"] <= GATE_REL_MAE
        and global_sum.get("bias_ratio") is not None
        and global_sum["bias_ratio"] <= GATE_BIAS_RATIO
        and growth_ok
        and v1_ok
    )

    approved: list[str] = []
    rejected: list[str] = []
    # Component approval from stratum passes
    component_status: dict[str, bool] = {}
    for s, block in by_stratum.items():
        comp = STRATUM_TO_COMPONENT.get(s)
        if not comp:
            continue
        component_status.setdefault(comp, True)
        if not block.get("pass"):
            component_status[comp] = False
    for comp, ok in component_status.items():
        if ok:
            approved.append(comp)
        else:
            rejected.append(comp)

    # Full approval requires load + warm_prompt_eval/prompt_eval + ≥1 tail
    has_load = "load" in approved
    has_prompt = "warm_prompt_eval" in approved or "prompt_eval" in approved
    has_tail = any(c.startswith("tail_") for c in approved)
    full = bool(global_ok and has_load and has_prompt and has_tail)

    status = (
        "accounting_predictor_v2_approved"
        if full
        else (
            "v2_partial_component_approval"
            if approved
            else "v2_live_shadow_failed"
        )
    )
    if full:
        live_status = "v2_live_shadow_validated"
        approval_status = "accounting_predictor_v2_approved"
    elif global_ok:
        live_status = "v2_live_shadow_validated"
        approval_status = (
            "v2_partial_component_approval" if not full else "accounting_predictor_v2_approved"
        )
    elif approved:
        # Strata can pass individually even when global bias/growth fails
        live_status = "v2_live_shadow_failed"
        approval_status = "v2_partial_component_approval"
    else:
        live_status = "v2_live_shadow_failed"
        approval_status = "v2_live_shadow_failed"

    return {
        "ok": True,
        "live_status": live_status,
        "approval_status": approval_status,
        "status": approval_status if full else live_status,
        "global": global_sum,
        "global_pass": global_ok,
        "by_stratum": by_stratum,
        "error_growth": {
            "spearman_abs_err_vs_t_eval": rho,
            "pass": growth_ok,
            "threshold": GATE_SPEARMAN_ERR_GROWTH,
            "n_warm": len(warm),
        },
        "v1_non_degradation": {
            "pass": v1_ok,
            "mae_registry_j": v1_mae_reg,
            "mae_standalone_j": v1_mae_solo,
            "n": len(v1_rows),
            "max_ratio": GATE_V1_DEGRADATION,
        },
        "approved_components": sorted(set(approved)),
        "rejected_components": sorted(set(rejected)),
        "full_approval": full,
        "gates": {
            "median_eps": GATE_MEDIAN_EPS,
            "rel_mae": GATE_REL_MAE,
            "bias_ratio": GATE_BIAS_RATIO,
            "min_stratum_n": MIN_STRATUM_N,
            "min_total_n": MIN_TOTAL_N,
        },
    }
