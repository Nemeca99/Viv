#!/usr/bin/env python3
"""Offline explanatory audit for the token-matrix E_net results.

Loads existing session artifacts (no new plant run).
Audits candidates: eval_duration_s, actual_eval_tokens, tokens_per_s,
P_mean, gpu_temp_settle_c, num_predict (baseline).

Uses the same SNR/CV gates as the token matrix, re-applied on tertile bins.
Provides phase-energy decomposition and Spearman/Pearson r^2 rankings.
No multivariate fit, no predictor, no Master wiring.
"""
from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def extract_features(action: dict[str, Any], session_dir: Path) -> dict[str, Any]:
    """Return flat feature dict for one admission action, enriched from session artifact."""
    full: dict[str, Any] = {}
    sid = action.get("session_id")
    if sid:
        art = session_dir / sid / "controlled_action_v2.json"
        if art.exists():
            import json
            full = json.loads(art.read_text(encoding="utf-8"))

    infer = full.get("infer") or {}
    temps = full.get("temperatures") or {}

    eval_count = infer.get("eval_count")
    eval_dur = infer.get("eval_duration_s")
    prompt_eval_dur = infer.get("prompt_eval_duration_s")
    load_dur = infer.get("load_duration_s")
    total_dur = infer.get("total_duration_s")

    tps = None
    if eval_count is not None and eval_dur and float(eval_dur) > 0:
        tps = float(eval_count) / float(eval_dur)

    E_net = (
        full.get("E_net_raw_j")
        or action.get("E_net_raw_j")
        or action.get("E_net_j")
    )
    E_gen = full.get("E_generate_j") or action.get("E_generate_j")
    dt_gen = full.get("delta_t_generate_s") or action.get("delta_t_generate_s")
    P_mean = full.get("P_mean_from_E_w") or action.get("P_mean_from_E_w")
    if P_mean is None and E_gen is not None and dt_gen:
        P_mean = float(E_gen) / float(dt_gen)

    P_active_net = None
    if E_net is not None and dt_gen and float(dt_gen) > 0:
        P_active_net = float(E_net) / float(dt_gen)

    # Phase-energy decomposition (P_active_net × phase_duration)
    E_load = _phase_energy(P_active_net, load_dur)
    E_prompt_eval = _phase_energy(P_active_net, prompt_eval_dur)
    E_token_eval = _phase_energy(P_active_net, eval_dur)
    E_phases_sum = _sum_none(E_load, E_prompt_eval, E_token_eval)
    E_residual = (
        float(E_net) - float(E_phases_sum)
        if E_net is not None and E_phases_sum is not None
        else None
    )

    cg = full.get("control_gates") or {}

    return {
        # identity
        "session_id": sid,
        "num_predict": action.get("num_predict"),
        "cell_id": action.get("cell_id") or (action.get("cell") or {}).get("cell_id"),
        "session_i": action.get("session_i"),
        "order_i": action.get("order_i"),
        # outcome variable
        "E_net_raw_j": float(E_net) if E_net is not None else None,
        "E_generate_j": float(E_gen) if E_gen is not None else None,
        "delta_t_generate_s": float(dt_gen) if dt_gen is not None else None,
        # candidates
        "eval_duration_s": float(eval_dur) if eval_dur is not None else None,
        "prompt_eval_duration_s": float(prompt_eval_dur) if prompt_eval_dur is not None else None,
        "load_duration_s": float(load_dur) if load_dur is not None else None,
        "total_duration_s": float(total_dur) if total_dur is not None else None,
        "actual_eval_tokens": int(eval_count) if eval_count is not None else None,
        "tokens_per_s": tps,
        "P_mean_w": float(P_mean) if P_mean is not None else None,
        "gpu_temp_settle_c": temps.get("gpu_temp_c_settle"),
        "gpu_temp_end_c": temps.get("gpu_temp_c_end"),
        # decomposition
        "P_active_net_w": P_active_net,
        "E_load_j": E_load,
        "E_prompt_eval_j": E_prompt_eval,
        "E_token_eval_j": E_token_eval,
        "E_phases_sum_j": E_phases_sum,
        "E_residual_j": E_residual,
        # control context
        "settle_ok": cg.get("settle_ok"),
        "CV_P_idle": cg.get("CV_P_idle"),
        "integration_wall_ratio": cg.get("integration_wall_ratio"),
        "sigma_baseline_subtraction_est_j": cg.get("sigma_baseline_subtraction_est_j"),
    }


def _phase_energy(P_net: float | None, t: Any) -> float | None:
    if P_net is None or t is None:
        return None
    try:
        return float(P_net) * float(t)
    except (TypeError, ValueError):
        return None


def _sum_none(*vals) -> float | None:
    out = 0.0
    for v in vals:
        if v is None:
            return None
        out += float(v)
    return out


# ---------------------------------------------------------------------------
# Correlation (descriptive only)
# ---------------------------------------------------------------------------

def _spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    rx = _ranks(xs)
    ry = _ranks(ys)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry))
    denom = n * (n ** 2 - 1)
    if denom == 0:
        return None
    return 1.0 - 6.0 * d2 / denom


def _pearson_r2(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx < 1e-12 or dy < 1e-12:
        return None
    r = num / (dx * dy)
    return r * r


def _ranks(xs: list[float]) -> list[float]:
    n = len(xs)
    order = sorted(range(n), key=lambda i: xs[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and xs[order[j]] == xs[order[i]]:
            j += 1
        avg = (i + j + 1) / 2.0
        for k in range(i, j):
            ranks[order[k]] = avg
        i = j
    return ranks


def correlate_candidates(
    features: list[dict[str, Any]],
    candidates: list[str],
    outcome: str = "E_net_raw_j",
) -> list[dict[str, Any]]:
    results = []
    ys = [f[outcome] for f in features if f.get(outcome) is not None]
    y_idx = [i for i, f in enumerate(features) if f.get(outcome) is not None]
    for cand in candidates:
        xs_full = [features[i].get(cand) for i in y_idx]
        paired = [(x, ys[j]) for j, x in enumerate(xs_full) if x is not None]
        if len(paired) < 3:
            results.append({"candidate": cand, "n": len(paired), "spearman": None, "r2": None})
            continue
        xs, ys2 = zip(*paired)
        results.append(
            {
                "candidate": cand,
                "n": len(paired),
                "spearman": _spearman(list(xs), list(ys2)),
                "r2": _pearson_r2(list(xs), list(ys2)),
            }
        )
    return sorted(results, key=lambda r: -(r.get("r2") or 0.0))


# ---------------------------------------------------------------------------
# Tertile binning + gate reuse
# ---------------------------------------------------------------------------

def _tertile_bins(
    features: list[dict[str, Any]], candidate: str
) -> list[list[dict[str, Any]]] | None:
    """Sort by candidate, split into 3 equal-count bins. Return None if not enough contrast."""
    valid = [f for f in features if f.get(candidate) is not None]
    n = len(valid)
    if n < 9:
        return None
    valid.sort(key=lambda f: float(f[candidate]))
    k = n // 3
    bins = [valid[:k], valid[k : 2 * k], valid[2 * k :]]
    # Check bins have distinct medians (rough contrast check)
    meds = [float(b[len(b) // 2][candidate]) for b in bins]
    if meds[0] == meds[-1]:
        return None  # insufficient_bin_contrast
    return bins


def _row_for_eval(feat: dict[str, Any]) -> dict[str, Any]:
    """Convert feature dict into the row schema expected by evaluate_control_repeats."""
    cg = {
        "settle_ok": feat.get("settle_ok", True),
        "CV_P_idle_ok": (
            feat.get("CV_P_idle") is not None and float(feat["CV_P_idle"]) <= 0.10
        ),
        "integration_wall_ratio": feat.get("integration_wall_ratio"),
        "integration_wall_ratio_ok": (
            feat.get("integration_wall_ratio") is not None
            and 0.85 <= float(feat["integration_wall_ratio"]) <= 1.25
        ),
        "sigma_baseline_subtraction_est_j": feat.get("sigma_baseline_subtraction_est_j"),
    }
    return {
        "E_net_raw_j": feat.get("E_net_raw_j"),
        "E_net_j": feat.get("E_net_raw_j"),
        "E_generate_j": feat.get("E_generate_j"),
        "P_mean_from_E_w": feat.get("P_mean_w"),
        "P_peak_generate_w": feat.get("P_mean_w"),  # fallback; peak not available offline
        "n_generate_locked_samples": 25,  # nominal; not material for offline audit
        "delta_t_generate_s": feat.get("delta_t_generate_s") or 3.0,
        "control_gates": cg,
    }


def evaluate_bins(
    bins: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    from lib.rid_electrical_ledger_controls import evaluate_control_repeats

    results = []
    for i, b in enumerate(bins):
        rows = [_row_for_eval(f) for f in b]
        ev = evaluate_control_repeats(rows, cv_p_primary="mean_from_E")
        ev["bin_i"] = i
        ev["n_actions"] = len(b)
        ev["bin_candidate_range"] = None  # filled by caller
        results.append(ev)
    return results


def _pooled_sigma(sig_a: float | None, n_a: int, sig_b: float | None, n_b: int) -> float | None:
    if sig_a is None or sig_b is None or n_a < 2 or n_b < 2:
        return None
    num = (n_a - 1) * sig_a ** 2 + (n_b - 1) * sig_b ** 2
    den = n_a + n_b - 2
    if den <= 0:
        return None
    return math.sqrt(num / den)


def separability_bins(bin_evals: list[dict[str, Any]]) -> dict[str, Any]:
    passing = [b for b in bin_evals if b.get("outcome") == "net_signature_repeatable"]
    pairs = []
    n_sep = 0
    for i in range(len(passing)):
        for j in range(i + 1, len(passing)):
            a, b = passing[i], passing[j]
            mu_a = a.get("mu_E_net_raw_j")
            mu_b = b.get("mu_E_net_raw_j")
            if mu_a is None or mu_b is None:
                continue
            delta = abs(float(mu_a) - float(mu_b))
            pooled = _pooled_sigma(
                a.get("sigma_E_net_raw_j"), int(a.get("n_usable") or 0),
                b.get("sigma_E_net_raw_j"), int(b.get("n_usable") or 0),
            )
            sep = pooled is not None and delta > pooled
            if sep:
                n_sep += 1
            pairs.append(
                {
                    "bin_a": a.get("bin_i"),
                    "bin_b": b.get("bin_i"),
                    "mu_a": mu_a,
                    "mu_b": mu_b,
                    "abs_delta": delta,
                    "pooled_sigma": pooled,
                    "separable": bool(sep),
                }
            )
    return {
        "n_passing_bins": len(passing),
        "n_pairs": len(pairs),
        "n_separable_pairs": n_sep,
        "all_pairs_separable": len(pairs) > 0 and n_sep == len(pairs),
        "pairs": pairs,
    }


CANDIDATE_KEYS = [
    "eval_duration_s",
    "actual_eval_tokens",
    "tokens_per_s",
    "P_mean_w",
    "gpu_temp_settle_c",
    "num_predict",
    "total_duration_s",
    "prompt_eval_duration_s",
]


def _is_monotone(bin_evals: list[dict[str, Any]], candidate_bins: list[list[dict[str, Any]]]) -> bool:
    """Check μ(E_net) increases with bin index (bins sorted ascending by candidate)."""
    mus = []
    for b in bin_evals:
        mu = b.get("mu_E_net_raw_j")
        if mu is not None:
            mus.append(float(mu))
    return len(mus) >= 2 and all(mus[i] < mus[i + 1] for i in range(len(mus) - 1))


def classify_candidate(
    bin_evals: list[dict[str, Any]],
    sep: dict[str, Any],
    candidate_bins: list[list[dict[str, Any]]],
) -> str:
    all_rep = all(b.get("outcome") == "net_signature_repeatable" for b in bin_evals)
    some_rep = any(b.get("outcome") == "net_signature_repeatable" for b in bin_evals)
    all_sep = bool(sep.get("all_pairs_separable"))
    mono = _is_monotone(bin_evals, candidate_bins)
    if all_rep and all_sep and mono:
        return "single_factor_cost_model_justified_review"
    if some_rep and (all_sep or sep.get("n_separable_pairs", 0) > 0):
        return "promising_factor_needs_validation_run"
    return "ledger_descriptive_only_no_cost_model"


def run_audit(
    features: list[dict[str, Any]],
    baseline_decision: str = "accounting_stable_tokens_not_explanatory",
    candidates: list[str] | None = None,
) -> dict[str, Any]:
    if candidates is None:
        candidates = list(CANDIDATE_KEYS)

    correlations = correlate_candidates(features, candidates)

    # Phase energy summary
    decomp_rows = [
        {
            "session_id": f.get("session_id"),
            "num_predict": f.get("num_predict"),
            "E_net_raw_j": f.get("E_net_raw_j"),
            "E_load_j": f.get("E_load_j"),
            "E_prompt_eval_j": f.get("E_prompt_eval_j"),
            "E_token_eval_j": f.get("E_token_eval_j"),
            "E_residual_j": f.get("E_residual_j"),
            "eval_duration_s": f.get("eval_duration_s"),
            "actual_eval_tokens": f.get("actual_eval_tokens"),
        }
        for f in features
    ]

    candidate_results: list[dict[str, Any]] = []
    best_candidates: list[str] = []

    for cand in candidates:
        bins = _tertile_bins(features, cand)
        if bins is None:
            candidate_results.append(
                {
                    "candidate": cand,
                    "status": "insufficient_bin_contrast",
                    "bin_evals": [],
                    "separability": {},
                    "classification": "ledger_descriptive_only_no_cost_model",
                }
            )
            continue

        bin_evals = evaluate_bins(bins)
        # Annotate bin range
        for i, (b, ev) in enumerate(zip(bins, bin_evals)):
            vals = [float(f[cand]) for f in b if f.get(cand) is not None]
            ev["bin_candidate_range"] = [min(vals), max(vals)] if vals else None
            ev["bin_i"] = i

        sep = separability_bins(bin_evals)
        classification = classify_candidate(bin_evals, sep, bins)
        if classification != "ledger_descriptive_only_no_cost_model":
            best_candidates.append(cand)
        candidate_results.append(
            {
                "candidate": cand,
                "status": "ok",
                "bin_evals": [
                    {
                        "bin_i": b.get("bin_i"),
                        "n_actions": b.get("n_actions"),
                        "bin_candidate_range": b.get("bin_candidate_range"),
                        "outcome": b.get("outcome"),
                        "mu_E_net_raw_j": b.get("mu_E_net_raw_j"),
                        "sigma_E_net_raw_j": b.get("sigma_E_net_raw_j"),
                        "CV_E": b.get("CV_E"),
                        "SNR_net": b.get("SNR_net"),
                        "CV_P": b.get("CV_P"),
                    }
                    for b in bin_evals
                ],
                "separability": sep,
                "classification": classification,
            }
        )

    # Rank candidates by best classification then top r2
    corr_map = {c["candidate"]: c for c in correlations}
    candidate_results.sort(
        key=lambda x: (
            {"single_factor_cost_model_justified_review": 0,
             "promising_factor_needs_validation_run": 1,
             "ledger_descriptive_only_no_cost_model": 2,
             "insufficient_bin_contrast": 3}.get(x.get("classification", ""), 3),
            -(corr_map.get(x["candidate"], {}).get("r2") or 0.0),
        )
    )

    top = candidate_results[0] if candidate_results else {}
    overall_decision: str
    if top.get("classification") == "single_factor_cost_model_justified_review":
        overall_decision = "single_factor_cost_model_justified_review"
    elif best_candidates:
        overall_decision = "promising_factor_needs_validation_run"
    else:
        overall_decision = "ledger_descriptive_only_no_cost_model"

    return {
        "ok": True,
        "token_baseline_decision": baseline_decision,
        "n_features": len(features),
        "candidates_audited": candidates,
        "correlations": correlations,
        "decomposition_rows": decomp_rows,
        "candidate_results": candidate_results,
        "best_candidates": best_candidates,
        "overall_decision": overall_decision,
        "learning_admission_withheld": True,
        "auto_admit": False,
        "predictor_authorized": False,
        "note": (
            "Offline replay of existing matrix actions. "
            "No new plant run, no multivariate fit, no Master wiring. "
            "single_factor_cost_model_justified_review only authorizes a "
            "dedicated validation plant run — not a predictor."
        ),
    }
