#!/usr/bin/env python3
"""Session-safe V2 fit, ablation, LOSO stability, and V1 overlap compare.

Train sessions {1,2,3}, selection {4}, final holdout {5}.
Never splits rows from the same session across folds.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Sequence

import numpy as np

from lib.rid_electrical_predictor import (
    DOMAIN_MAX_S,
    DOMAIN_MIN_S,
    predict_E_net as predict_E_net_v1,
)
from lib.rid_electrical_predictor_v2 import (
    TAIL_HORIZONS_S,
    residency_is_cold,
)

# Pre-locked gates
GATE_MEDIAN_EPS = 0.15
GATE_REL_MAE = 0.15
GATE_MAE_J = 120.0
GATE_LOSO_CV = 0.25
GATE_BIAS_RATIO = 0.50
GATE_COLD_WARM_REL = 0.20
TOKEN_ABLATION_MIN_REL_GAIN = 0.05

TRAIN_SESSIONS = frozenset({1, 2, 3})
SELECT_SESSIONS = frozenset({4})
HOLDOUT_SESSIONS = frozenset({5})


def extract_feature_row(r: dict[str, Any]) -> dict[str, Any] | None:
    infer = r.get("infer") or {}
    te = infer.get("eval_duration_s")
    tp = infer.get("prompt_eval_duration_s")
    if te is None or r.get("E_net_raw_j") is None or r.get("E_tail_j") is None:
        return None
    if tp is None:
        tp = 0.0
    th = r.get("tail_tau_s")
    if th is None:
        th = 5.0
    residency = r.get("residency") or (r.get("cell") or {}).get("residency")
    cold = residency_is_cold(
        residency,
        unload_before=bool(r.get("unload_before")),
        cell_id=str(r.get("cell_id") or ""),
    )
    e_net = float(r["E_net_raw_j"])
    e_tail = float(r["E_tail_j"])
    return {
        "session_i": int(r["session_i"]) if r.get("session_i") is not None else None,
        "cell_id": r.get("cell_id"),
        "decomp_family": r.get("decomp_family"),
        "residency": residency,
        "cold": cold,
        "t_eval_s": float(te),
        "t_prompt_s": float(tp),
        "tail_horizon_s": float(th),
        "E_net_j": e_net,
        "E_tail_j": e_tail,
        "E_action_j": e_net + e_tail,
        "eval_count": infer.get("eval_count"),
        "prompt_eval_count": infer.get("prompt_eval_count"),
    }


def featurize_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        fr = extract_feature_row(r)
        if fr is not None and fr.get("session_i") is not None:
            out.append(fr)
    return out


def session_split(
    feats: Sequence[dict[str, Any]],
    *,
    train: frozenset[int] = TRAIN_SESSIONS,
    select: frozenset[int] = SELECT_SESSIONS,
    holdout: frozenset[int] = HOLDOUT_SESSIONS,
) -> dict[str, Any]:
    buckets = {"train": [], "select": [], "holdout": [], "other": []}
    for f in feats:
        s = int(f["session_i"])
        if s in train:
            buckets["train"].append(f)
        elif s in select:
            buckets["select"].append(f)
        elif s in holdout:
            buckets["holdout"].append(f)
        else:
            buckets["other"].append(f)
    # Leak check
    def _ids(xs: list[dict[str, Any]]) -> set[int]:
        return {int(x["session_i"]) for x in xs}

    leak = (
        _ids(buckets["train"]) & _ids(buckets["select"])
        | _ids(buckets["train"]) & _ids(buckets["holdout"])
        | _ids(buckets["select"]) & _ids(buckets["holdout"])
    )
    return {
        **buckets,
        "leak_sessions": sorted(leak),
        "ok": len(leak) == 0
        and len(buckets["train"]) > 0
        and len(buckets["holdout"]) > 0,
    }


def nnls(X: np.ndarray, y: np.ndarray, *, max_iter: int = 200) -> np.ndarray:
    """Active-set non-negative least squares (Lawson-Hanson style, compact)."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float).reshape(-1)
    n_features = X.shape[1]
    P: set[int] = set()  # passive (free, positive)
    R = set(range(n_features))  # restricted to zero
    x = np.zeros(n_features, dtype=float)
    for _ in range(max_iter):
        resid = y - X @ x
        w = X.T @ resid
        if not R or w[list(R)].max(initial=0.0) <= 1e-12:
            break
        # Move largest positive gradient from R to P
        j = max(R, key=lambda i: w[i])
        R.remove(j)
        P.add(j)
        while True:
            if not P:
                break
            P_list = sorted(P)
            Xp = X[:, P_list]
            try:
                z_p, *_ = np.linalg.lstsq(Xp, y, rcond=None)
            except np.linalg.LinAlgError:
                z_p = np.zeros(len(P_list))
            z = np.zeros(n_features)
            for k, idx in enumerate(P_list):
                z[idx] = z_p[k]
            if np.all(z[P_list] >= -1e-12):
                x = np.maximum(z, 0.0)
                break
            # Find step to keep non-neg
            alphas = []
            for idx in P_list:
                if z[idx] < 0:
                    denom = x[idx] - z[idx]
                    if abs(denom) > 1e-18:
                        alphas.append(x[idx] / denom)
            if not alphas:
                x = np.maximum(z, 0.0)
                break
            alpha = min(alphas)
            x = x + alpha * (z - x)
            # Move near-zero to R
            for idx in list(P):
                if x[idx] <= 1e-12:
                    x[idx] = 0.0
                    P.remove(idx)
                    R.add(idx)
    return np.maximum(x, 0.0)


def estimate_tail_lookup(train_feats: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Non-negative E_tail(h) from train mean measured tails per horizon."""
    buckets: dict[float, list[float]] = {h: [] for h in TAIL_HORIZONS_S}
    for f in train_feats:
        h = float(f["tail_horizon_s"])
        nearest = min(TAIL_HORIZONS_S, key=lambda hh: abs(hh - h))
        buckets[nearest].append(float(f["E_tail_j"]))
    out: dict[str, float] = {}
    for h in TAIL_HORIZONS_S:
        vals = buckets[h]
        out[str(float(h))] = float(statistics.fmean(vals)) if vals else 0.0
    # Enforce monotonic non-decreasing in h (physical cumulative tail)
    prev = 0.0
    for h in TAIL_HORIZONS_S:
        key = str(float(h))
        out[key] = max(float(out[key]), prev)
        prev = out[key]
    return out


def _design_matrix_net(
    feats: Sequence[dict[str, Any]],
    *,
    include_tokens: bool = False,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Net-only design: cold, t_prompt, t_eval [, token counts]. Target = E_net."""
    names = [
        "E_load_cold_j",
        "beta_prompt_j_per_s",
        "beta_eval_j_per_s",
    ]
    if include_tokens:
        names.extend(["gamma_eval_tokens_j", "gamma_prompt_tokens_j"])
    rows = []
    ys = []
    for f in feats:
        row = [
            1.0 if f["cold"] else 0.0,
            float(f["t_prompt_s"]),
            float(f["t_eval_s"]),
        ]
        if include_tokens:
            row.append(float(f.get("eval_count") or 0.0))
            row.append(float(f.get("prompt_eval_count") or 0.0))
        rows.append(row)
        ys.append(float(f["E_net_j"]))
    return np.asarray(rows, dtype=float), np.asarray(ys, dtype=float), names


def coeffs_from_beta(
    beta: np.ndarray,
    names: list[str],
    *,
    tail_by_h: dict[str, float],
) -> dict[str, Any]:
    d = {n: float(beta[i]) for i, n in enumerate(names)}
    return {
        "E_load_cold_j": d.get("E_load_cold_j", 0.0),
        "beta_prompt_j_per_s": d.get("beta_prompt_j_per_s", 0.0),
        "beta_eval_j_per_s": d.get("beta_eval_j_per_s", 0.0),
        "E_tail_by_horizon_j": {str(k): float(v) for k, v in tail_by_h.items()},
        "gamma_eval_tokens_j": d.get("gamma_eval_tokens_j"),
        "gamma_prompt_tokens_j": d.get("gamma_prompt_tokens_j"),
        "include_tokens": "gamma_eval_tokens_j" in d,
        "tail_method": "train_mean_monotonic_interp",
    }


def predict_feats(
    feats: Sequence[dict[str, Any]], coeffs: dict[str, Any]
) -> list[dict[str, Any]]:
    from lib.rid_electrical_predictor_v2 import interpolate_tail

    out = []
    for f in feats:
        e_load = float(coeffs["E_load_cold_j"]) if f["cold"] else 0.0
        e_prompt = float(coeffs["beta_prompt_j_per_s"]) * float(f["t_prompt_s"])
        e_eval = float(coeffs["beta_eval_j_per_s"]) * float(f["t_eval_s"])
        if coeffs.get("include_tokens"):
            e_eval += float(coeffs.get("gamma_eval_tokens_j") or 0.0) * float(
                f.get("eval_count") or 0.0
            )
            e_prompt += float(coeffs.get("gamma_prompt_tokens_j") or 0.0) * float(
                f.get("prompt_eval_count") or 0.0
            )
        e_tail = interpolate_tail(
            float(f["tail_horizon_s"]), coeffs["E_tail_by_horizon_j"]
        )
        e_tail = float(e_tail or 0.0)
        e_net = e_load + e_prompt + e_eval
        e_hat = e_net + e_tail
        e_meas = float(f["E_action_j"])
        eps = abs(e_meas - e_hat) / (abs(e_meas) if abs(e_meas) > 1e-9 else 1e-9)
        out.append(
            {
                **{k: f[k] for k in ("session_i", "cell_id", "cold", "decomp_family")},
                "E_meas_j": e_meas,
                "E_hat_j": e_hat,
                "E_net_meas_j": f["E_net_j"],
                "E_net_hat_j": e_net,
                "residual_j": e_meas - e_hat,
                "eps_closure": eps,
                "abs_err_j": abs(e_meas - e_hat),
                "t_eval_s": f["t_eval_s"],
                "t_prompt_s": f["t_prompt_s"],
            }
        )
    return out


def summarize_errors(preds: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not preds:
        return {
            "n": 0,
            "mae_j": None,
            "rmse_j": None,
            "rel_mae": None,
            "median_eps": None,
            "mean_eps": None,
            "mean_residual_j": None,
            "bias_ratio": None,
        }
    abs_err = [float(p["abs_err_j"]) for p in preds]
    eps = [float(p["eps_closure"]) for p in preds]
    resid = [float(p["residual_j"]) for p in preds]
    meas = [float(p["E_meas_j"]) for p in preds]
    mae = statistics.fmean(abs_err)
    rmse = math.sqrt(statistics.fmean([e * e for e in abs_err]))
    rel_mae = statistics.fmean(
        [a / (abs(m) if abs(m) > 1e-9 else 1e-9) for a, m in zip(abs_err, meas)]
    )
    mu_r = statistics.fmean(resid)
    return {
        "n": len(preds),
        "mae_j": mae,
        "rmse_j": rmse,
        "rel_mae": rel_mae,
        "median_eps": statistics.median(eps),
        "mean_eps": statistics.fmean(eps),
        "mean_residual_j": mu_r,
        "bias_ratio": abs(mu_r) / mae if mae > 1e-12 else None,
    }


def fit_model(
    train_feats: Sequence[dict[str, Any]], *, include_tokens: bool = False
) -> dict[str, Any]:
    """Two-stage: train-mean E_tail(h), then NNLS net = load + βp tp + βe te."""
    if len(train_feats) < 6:
        return {"ok": False, "reason": "insufficient_train", "n": len(train_feats)}
    tail_by_h = estimate_tail_lookup(train_feats)
    X, y, names = _design_matrix_net(train_feats, include_tokens=include_tokens)
    if len(y) < max(3, X.shape[1]):
        return {"ok": False, "reason": "insufficient_train", "n": len(y)}
    beta = nnls(X, y)
    coeffs = coeffs_from_beta(beta, names, tail_by_h=tail_by_h)
    neg = {
        k: v
        for k, v in {
            "E_load_cold_j": coeffs["E_load_cold_j"],
            "beta_prompt_j_per_s": coeffs["beta_prompt_j_per_s"],
            "beta_eval_j_per_s": coeffs["beta_eval_j_per_s"],
            **{f"tail_{k}": v for k, v in coeffs["E_tail_by_horizon_j"].items()},
        }.items()
        if v is not None and float(v) < -1e-9
    }
    return {
        "ok": True,
        "coefficients": coeffs,
        "feature_names": names,
        "beta": [float(x) for x in beta],
        "n_train": len(y),
        "negative_components": neg,
        "nonnegative_ok": len(neg) == 0,
        "fit_stages": ["tail_train_mean", "net_nnls"],
    }


def loso_stability(feats: Sequence[dict[str, Any]]) -> dict[str, Any]:
    sessions = sorted({int(f["session_i"]) for f in feats})
    betas_eval: list[float] = []
    betas_prompt: list[float] = []
    loads: list[float] = []
    folds = []
    for hold in sessions:
        train = [f for f in feats if int(f["session_i"]) != hold]
        fit = fit_model(train, include_tokens=False)
        if not fit.get("ok"):
            continue
        c = fit["coefficients"]
        betas_eval.append(float(c["beta_eval_j_per_s"]))
        betas_prompt.append(float(c["beta_prompt_j_per_s"]))
        loads.append(float(c["E_load_cold_j"]))
        folds.append({"holdout_session": hold, "coefficients": c})

    def _cv(xs: list[float]) -> float | None:
        if len(xs) < 2:
            return None
        mu = statistics.fmean(xs)
        if abs(mu) < 1e-9:
            return None
        return statistics.pstdev(xs) / abs(mu)

    cv_e = _cv(betas_eval)
    cv_p = _cv(betas_prompt)
    mu_p = statistics.fmean(betas_prompt) if betas_prompt else 0.0
    # Prompt slope may be near-zero (below resolution); then CV is undefined — treat as OK
    prompt_ok = (cv_p is not None and cv_p <= GATE_LOSO_CV) or abs(mu_p) < 1.0
    eval_ok = cv_e is not None and cv_e <= GATE_LOSO_CV
    return {
        "n_folds": len(folds),
        "cv_beta_eval": cv_e,
        "cv_beta_prompt": cv_p,
        "cv_E_load_cold": _cv(loads),
        "mean_beta_prompt": mu_p,
        "folds": folds,
        "stability_pass": bool(eval_ok and prompt_ok),
    }


def v1_overlap_compare(feats: Sequence[dict[str, Any]], coeffs: dict[str, Any]) -> dict[str, Any]:
    """Warm-resident, t_eval in [2.5, 4.5], compare MAE on E_net."""
    overlap = [
        f
        for f in feats
        if (not f["cold"])
        and DOMAIN_MIN_S <= float(f["t_eval_s"]) <= DOMAIN_MAX_S
    ]
    v1_errs = []
    v2_errs = []
    rows = []
    for f in overlap:
        v1 = predict_E_net_v1(float(f["t_eval_s"]))
        v1_hat = v1.get("predicted_E_net_j")
        e_load = 0.0
        e_prompt = float(coeffs["beta_prompt_j_per_s"]) * float(f["t_prompt_s"])
        e_eval = float(coeffs["beta_eval_j_per_s"]) * float(f["t_eval_s"])
        v2_hat = e_load + e_prompt + e_eval
        meas = float(f["E_net_j"])
        if v1_hat is None:
            continue
        e1 = abs(meas - float(v1_hat))
        e2 = abs(meas - float(v2_hat))
        v1_errs.append(e1)
        v2_errs.append(e2)
        rows.append(
            {
                "cell_id": f.get("cell_id"),
                "t_eval_s": f["t_eval_s"],
                "E_net_j": meas,
                "v1_hat_j": float(v1_hat),
                "v2_hat_j": float(v2_hat),
                "abs_err_v1": e1,
                "abs_err_v2": e2,
            }
        )
    mae_v1 = statistics.fmean(v1_errs) if v1_errs else None
    mae_v2 = statistics.fmean(v2_errs) if v2_errs else None
    delta = None if mae_v1 is None or mae_v2 is None else float(mae_v1) - float(mae_v2)
    return {
        "n_overlap": len(rows),
        "mae_v1_j": mae_v1,
        "mae_v2_j": mae_v2,
        "delta_mae_j": delta,
        "v2_improves_overlap": bool(delta is not None and delta > 0),
        "rows": rows,
    }


def evaluate_gates(
    hold_sum: dict[str, Any],
    *,
    loso: dict[str, Any],
    cold_rel: float | None,
    warm_rel: float | None,
    nonnegative_ok: bool,
) -> dict[str, Any]:
    checks = {
        "median_eps_le_0_15": (
            hold_sum.get("median_eps") is not None
            and hold_sum["median_eps"] <= GATE_MEDIAN_EPS
        ),
        "rel_mae_le_0_15": (
            hold_sum.get("rel_mae") is not None and hold_sum["rel_mae"] <= GATE_REL_MAE
        ),
        "mae_le_120_j": (
            hold_sum.get("mae_j") is not None and hold_sum["mae_j"] <= GATE_MAE_J
        ),
        "loso_stability": bool(loso.get("stability_pass")),
        "bias_ratio_le_0_50": (
            hold_sum.get("bias_ratio") is not None
            and hold_sum["bias_ratio"] <= GATE_BIAS_RATIO
        ),
        "cold_rel_mae_le_0_20": cold_rel is not None and cold_rel <= GATE_COLD_WARM_REL,
        "warm_rel_mae_le_0_20": warm_rel is not None and warm_rel <= GATE_COLD_WARM_REL,
        "nonnegative_ok": bool(nonnegative_ok),
    }
    return {
        "checks": checks,
        "all_pass": all(checks.values()),
        "thresholds": {
            "median_eps": GATE_MEDIAN_EPS,
            "rel_mae": GATE_REL_MAE,
            "mae_j": GATE_MAE_J,
            "loso_cv": GATE_LOSO_CV,
            "bias_ratio": GATE_BIAS_RATIO,
            "cold_warm_rel": GATE_COLD_WARM_REL,
        },
    }


def decision_ladder(
    *,
    gates_pass: bool,
    overlap: dict[str, Any],
    expands_coverage: bool = True,
) -> dict[str, Any]:
    """Locked ladder outcomes."""
    improves = bool(overlap.get("v2_improves_overlap"))
    if not gates_pass:
        decision = "retain_v1_decomposition_diagnostic_only"
        proceed = False
    elif improves and expands_coverage:
        decision = "v2_improves_overlap_and_expands_coverage"
        proceed = True
    elif expands_coverage and not improves:
        decision = "keep_both_domain_registry"
        proceed = True  # still allow prospective; V1 remains fallback
    else:
        decision = "retain_v1_decomposition_diagnostic_only"
        proceed = False
    return {
        "decision": decision,
        "proceed_to_prospective": proceed,
        "v2_improves_overlap": improves,
        "expands_coverage": expands_coverage,
    }


def run_v2_fit_pipeline(raw_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    feats = featurize_rows(raw_rows)
    split = session_split(feats)
    if not split.get("ok"):
        return {"ok": False, "error": "session_split_failed", "split": split}

    # Primary duration-only fit on train
    fit_dur = fit_model(split["train"], include_tokens=False)
    if not fit_dur.get("ok"):
        return {"ok": False, "error": "fit_failed", "fit": fit_dur}

    # Token ablation on selection fold
    fit_tok = fit_model(split["train"], include_tokens=True)
    sel_dur = summarize_errors(
        predict_feats(split["select"], fit_dur["coefficients"])
    )
    sel_tok = (
        summarize_errors(predict_feats(split["select"], fit_tok["coefficients"]))
        if fit_tok.get("ok")
        else {"mae_j": None}
    )
    keep_tokens = False
    if (
        fit_tok.get("ok")
        and sel_dur.get("mae_j")
        and sel_tok.get("mae_j")
        and sel_dur["mae_j"] > 1e-9
    ):
        gain = (sel_dur["mae_j"] - sel_tok["mae_j"]) / sel_dur["mae_j"]
        keep_tokens = gain >= TOKEN_ABLATION_MIN_REL_GAIN and fit_tok.get(
            "nonnegative_ok", False
        )
    chosen = fit_tok if keep_tokens else fit_dur
    coeffs = chosen["coefficients"]
    coeffs["include_tokens"] = keep_tokens
    coeffs["heldout_rmse_j"] = None  # filled after holdout

    hold_preds = predict_feats(split["holdout"], coeffs)
    hold_sum = summarize_errors(hold_preds)
    coeffs["heldout_rmse_j"] = hold_sum.get("rmse_j")

    cold_preds = [p for p in hold_preds if p.get("cold")]
    warm_preds = [p for p in hold_preds if not p.get("cold")]
    cold_rel = summarize_errors(cold_preds).get("rel_mae")
    warm_rel = summarize_errors(warm_preds).get("rel_mae")

    loso = loso_stability(feats)
    gates = evaluate_gates(
        hold_sum,
        loso=loso,
        cold_rel=cold_rel,
        warm_rel=warm_rel,
        nonnegative_ok=bool(chosen.get("nonnegative_ok")),
    )

    # Refit on train+select for candidate coeffs if gates pass (holdout untouched)
    final_fit = fit_model(
        split["train"] + split["select"], include_tokens=keep_tokens
    )
    final_coeffs = (
        final_fit["coefficients"] if final_fit.get("ok") else coeffs
    )
    final_coeffs["include_tokens"] = keep_tokens
    final_coeffs["heldout_rmse_j"] = hold_sum.get("rmse_j")
    final_coeffs["formula"] = (
        "E_action = E_load(cold) + beta_prompt*t_prompt + beta_eval*t_eval + E_tail(h)"
        + (" + token_terms" if keep_tokens else "")
    )

    overlap = v1_overlap_compare(feats, final_coeffs)
    expands = True  # V2 covers load/prompt/tail by construction
    ladder = decision_ladder(
        gates_pass=bool(gates.get("all_pass")),
        overlap=overlap,
        expands_coverage=expands,
    )

    return {
        "ok": True,
        "n_features": len(feats),
        "split": {
            "train_sessions": sorted(TRAIN_SESSIONS),
            "select_sessions": sorted(SELECT_SESSIONS),
            "holdout_sessions": sorted(HOLDOUT_SESSIONS),
            "n_train": len(split["train"]),
            "n_select": len(split["select"]),
            "n_holdout": len(split["holdout"]),
            "leak_sessions": split["leak_sessions"],
        },
        "ablation": {
            "duration_only_select": sel_dur,
            "duration_plus_tokens_select": sel_tok,
            "keep_tokens": keep_tokens,
            "min_rel_gain": TOKEN_ABLATION_MIN_REL_GAIN,
        },
        "fit_train": fit_dur,
        "coefficients": final_coeffs,
        "holdout_summary": hold_sum,
        "holdout_predictions": hold_preds,
        "cold_holdout_rel_mae": cold_rel,
        "warm_holdout_rel_mae": warm_rel,
        "loso": {
            "n_folds": loso.get("n_folds"),
            "cv_beta_eval": loso.get("cv_beta_eval"),
            "cv_beta_prompt": loso.get("cv_beta_prompt"),
            "cv_E_load_cold": loso.get("cv_E_load_cold"),
            "stability_pass": loso.get("stability_pass"),
        },
        "gates": gates,
        "v1_overlap_compare": {
            k: overlap[k]
            for k in (
                "n_overlap",
                "mae_v1_j",
                "mae_v2_j",
                "delta_mae_j",
                "v2_improves_overlap",
            )
        },
        "decision_ladder": ladder,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "accounting_predictor_v2_approved": False,
            "predictor_v1_frozen": True,
        },
    }
