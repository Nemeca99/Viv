#!/usr/bin/env python3
"""Throughput-derived fair pre-action baseline using frozen V1 coefficients."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from lib.rid_electrical_predictor import ALPHA, BETA, DOMAIN_MAX_S, DOMAIN_MIN_S

MIN_THROUGHPUT_HISTORY = 5
TRAILING_WINDOW = 20


def trailing_throughput_tps(
    history: Sequence[Mapping[str, Any]],
    *,
    plant_config_id: str,
    model: str,
    residency: str = "warm_repeat",
    as_of_index: int | None = None,
    window: int = TRAILING_WINDOW,
    min_history: int = MIN_THROUGHPUT_HISTORY,
) -> tuple[float | None, int]:
    """Median tokens/s of previous eligible actions (strictly past-only).

    history rows need: plant_config_id, model, residency, tokens_per_s (or
    actual_eval_tokens / eval_duration_s), and are assumed chronological.
    """
    end = len(history) if as_of_index is None else int(as_of_index)
    prior = []
    for r in history[:end]:
        if str(r.get("plant_config_id") or "") != plant_config_id:
            continue
        if str(r.get("model") or r.get("model_id") or "") != model:
            continue
        if str(r.get("residency") or r.get("residency_state") or "") != residency:
            continue
        tps = r.get("tokens_per_s")
        if tps is None:
            toks = r.get("actual_eval_tokens")
            dur = r.get("eval_duration_s")
            try:
                if toks is not None and dur is not None and float(dur) > 0:
                    tps = float(toks) / float(dur)
            except (TypeError, ValueError):
                tps = None
        try:
            tv = float(tps) if tps is not None else None
        except (TypeError, ValueError):
            tv = None
        if tv is None or not math.isfinite(tv) or tv <= 0:
            continue
        prior.append(tv)
    if len(prior) < min_history:
        return None, len(prior)
    windowed = prior[-window:]
    windowed_sorted = sorted(windowed)
    n = len(windowed_sorted)
    mid = n // 2
    if n % 2:
        med = windowed_sorted[mid]
    else:
        med = 0.5 * (windowed_sorted[mid - 1] + windowed_sorted[mid])
    return float(med), len(prior)


def baseline_predict_E_net(
    *,
    num_predict: int | float,
    trailing_throughput_tps: float | None,
    throughput_history_count: int | None = None,
    min_history: int = MIN_THROUGHPUT_HISTORY,
) -> dict[str, Any]:
    """Fair pre-action baseline: E = alpha + beta * (num_predict / tps)."""
    out: dict[str, Any] = {
        "predicted_E_net_j": None,
        "t_eval_hat_s": None,
        "confidence": "ok",
        "in_domain": False,
        "source": "throughput_v1_baseline",
        "alpha_j": ALPHA,
        "beta_j_per_s": BETA,
        "operational_authority": False,
        "master_routing_authorized": False,
        "gates_action": False,
    }
    hist_n = int(throughput_history_count if throughput_history_count is not None else 0)
    if trailing_throughput_tps is None or hist_n < min_history:
        out["confidence"] = "insufficient_throughput_history"
        return out
    try:
        tps = float(trailing_throughput_tps)
        npv = float(num_predict)
    except (TypeError, ValueError):
        out["confidence"] = "invalid_input"
        return out
    if tps <= 0 or not math.isfinite(tps) or not math.isfinite(npv):
        out["confidence"] = "invalid_input"
        return out
    t_hat = npv / tps
    out["t_eval_hat_s"] = t_hat
    if not (DOMAIN_MIN_S <= t_hat <= DOMAIN_MAX_S):
        out["confidence"] = "out_of_validated_domain"
        return out
    out["predicted_E_net_j"] = float(ALPHA) + float(BETA) * float(t_hat)
    out["in_domain"] = True
    return out


def paired_metrics(
    y_true: Sequence[float],
    y_pred: Sequence[float],
) -> dict[str, Any]:
    """RMSE/MAE/bias/calibration on paired predictions (nulls already dropped)."""
    import statistics

    n = len(y_true)
    if n == 0:
        return {
            "n": 0,
            "rmse": None,
            "mae": None,
            "rel_mae": None,
            "bias": None,
            "calibration_slope": None,
        }
    err = [float(p) - float(t) for t, p in zip(y_true, y_pred)]
    abs_err = [abs(e) for e in err]
    rmse = math.sqrt(statistics.fmean([e * e for e in err]))
    mae = statistics.fmean(abs_err)
    mean_abs_y = statistics.fmean([abs(float(t)) for t in y_true]) or 1.0
    rel_mae = mae / mean_abs_y
    bias = statistics.fmean(err)
    # calibration slope: cov(pred, true) / var(pred)
    mp = statistics.fmean(y_pred)
    mt = statistics.fmean(y_true)
    var_p = statistics.fmean([(p - mp) ** 2 for p in y_pred])
    if var_p <= 1e-18:
        slope = None
    else:
        cov = statistics.fmean([(p - mp) * (t - mt) for p, t in zip(y_pred, y_true)])
        slope = cov / var_p
    return {
        "n": n,
        "rmse": rmse,
        "mae": mae,
        "rel_mae": rel_mae,
        "bias": bias,
        "calibration_slope": slope,
        "bias_over_rmse": (abs(bias) / rmse) if rmse else None,
    }
