#!/usr/bin/env python3
"""Prospective eval_duration -> E_net validation (single-factor).

Tests: E_net ~= alpha + beta * eval_duration_s under fixed controls.
Session-level holdout only. Learning admission withheld by default.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Sequence

from lib.rid_electrical_ledger_controls import ControlCell, evaluate_control_repeats

# Nominal throughput from prior matrix (~103 tok/s). Used only to choose num_predict
# so measured eval_duration spans the target band — actual t_eval is measured.
NOMINAL_TOKENS_PER_S = 103.0

# Five duration targets spanning observed admission range (~2.45–4.48 s).
DURATION_TARGETS_S: tuple[float, ...] = (2.5, 3.0, 3.5, 4.0, 4.5)


def num_predict_for_target(t_eval_s: float, tps: float = NOMINAL_TOKENS_PER_S) -> int:
    """Map target eval duration to num_predict (control knob), rounded to int."""
    return max(64, int(round(float(t_eval_s) * float(tps))))


@dataclass(frozen=True)
class DurationCell:
    target_eval_s: float
    num_predict: int
    cell_id: str

    def to_control_cell(self) -> ControlCell:
        return ControlCell(
            cell_id=self.cell_id,
            residency="warm_repeat",
            num_predict=self.num_predict,
            token_bucket=f"teval_{self.target_eval_s:g}s",
        )


def make_duration_cells(
    targets: Sequence[float] = DURATION_TARGETS_S,
    tps: float = NOMINAL_TOKENS_PER_S,
) -> list[DurationCell]:
    cells: list[DurationCell] = []
    for t in targets:
        np_ = num_predict_for_target(t, tps=tps)
        cells.append(
            DurationCell(
                target_eval_s=float(t),
                num_predict=np_,
                cell_id=f"teval_{t:g}s_np{np_}__warm_repeat",
            )
        )
    return cells


def build_session_orders(
    cells: Sequence[DurationCell],
    n_sessions: int = 5,
) -> list[list[DurationCell]]:
    """Latin-style rotations: each session permutes cell order to avoid order confounds."""
    base = list(cells)
    n = len(base)
    if n == 0 or n_sessions < 1:
        return []
    orders: list[list[DurationCell]] = []
    for s in range(n_sessions):
        # Rotate left by s, then reverse every other session for extra mix.
        rot = base[s % n :] + base[: s % n]
        if s % 2 == 1:
            rot = list(reversed(rot))
        orders.append(rot)
    return orders


def rotation_coverage(orders: Sequence[Sequence[DurationCell]]) -> dict[str, Any]:
    if not orders:
        return {"ok": False, "reason": "empty_orders"}
    ids = [c.cell_id for c in orders[0]]
    counts: dict[str, int] = {cid: 0 for cid in ids}
    per_session_ok = True
    for order in orders:
        got = sorted(c.cell_id for c in order)
        if got != sorted(ids):
            per_session_ok = False
        for c in order:
            counts[c.cell_id] = counts.get(c.cell_id, 0) + 1
    n_sessions = len(orders)
    return {
        "ok": per_session_ok and all(v == n_sessions for v in counts.values()),
        "n_sessions": n_sessions,
        "counts": counts,
        "cell_ids": ids,
        "orders": [[c.cell_id for c in o] for o in orders],
    }


# ---------------------------------------------------------------------------
# Linear fit + diagnostics
# ---------------------------------------------------------------------------

def fit_alpha_beta(
    xs: Sequence[float], ys: Sequence[float]
) -> dict[str, Any]:
    """Ordinary least squares: y = alpha + beta * x."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return {"ok": False, "n": n, "alpha": None, "beta": None, "r2": None}
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx < 1e-18:
        return {"ok": False, "n": n, "alpha": None, "beta": None, "r2": None, "reason": "zero_var_x"}
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    beta = sxy / sxx
    alpha = my - beta * mx
    preds = [alpha + beta * x for x in xs]
    ss_res = sum((ys[i] - preds[i]) ** 2 for i in range(n))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = None if ss_tot < 1e-18 else 1.0 - ss_res / ss_tot
    return {
        "ok": True,
        "n": n,
        "alpha": alpha,
        "beta": beta,
        "r2": r2,
        "ss_res": ss_res,
        "ss_tot": ss_tot,
    }


def predict_rows(
    rows: Sequence[dict[str, Any]],
    alpha: float,
    beta: float,
    x_key: str = "eval_duration_s",
    y_key: str = "E_net_raw_j",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        x = r.get(x_key)
        y = r.get(y_key)
        if x is None or y is None:
            continue
        yhat = float(alpha) + float(beta) * float(x)
        resid = float(y) - yhat
        rel = abs(resid) / abs(float(y)) if abs(float(y)) > 1e-9 else None
        out.append(
            {
                "session_i": r.get("session_i"),
                "cell_id": r.get("cell_id"),
                "eval_duration_s": float(x),
                "E_net_raw_j": float(y),
                "E_hat_j": yhat,
                "residual_j": resid,
                "abs_rel_error": rel,
            }
        )
    return out


def summarize_predictions(preds: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not preds:
        return {
            "n": 0,
            "mae_j": None,
            "rmse_j": None,
            "mean_abs_rel_error": None,
            "median_abs_rel_error": None,
            "residual_vs_duration_slope": None,
            "error_grows_with_duration": None,
        }
    abs_err = [abs(p["residual_j"]) for p in preds]
    rel = [p["abs_rel_error"] for p in preds if p.get("abs_rel_error") is not None]
    xs = [p["eval_duration_s"] for p in preds]
    rs = [abs(p["residual_j"]) for p in preds]
    slope = None
    if len(xs) >= 3:
        fit = fit_alpha_beta(xs, rs)
        slope = fit.get("beta")
    return {
        "n": len(preds),
        "mae_j": statistics.fmean(abs_err),
        "rmse_j": math.sqrt(statistics.fmean([e * e for e in abs_err])),
        "mean_abs_rel_error": statistics.fmean(rel) if rel else None,
        "median_abs_rel_error": statistics.median(rel) if rel else None,
        "residual_vs_duration_slope": slope,
        "error_grows_with_duration": bool(slope is not None and slope > 0),
        "mu_residual_j": statistics.fmean([p["residual_j"] for p in preds]),
        "sigma_residual_j": statistics.pstdev([p["residual_j"] for p in preds])
        if len(preds) > 1
        else 0.0,
    }


def session_holdout_split(
    rows: Sequence[dict[str, Any]],
    *,
    holdout_sessions: Sequence[int] | None = None,
    holdout_fraction: float = 0.4,
) -> dict[str, Any]:
    """Split by whole session_i. Never mix rows from the same session across folds."""
    sessions = sorted({int(r["session_i"]) for r in rows if r.get("session_i") is not None})
    if not sessions:
        return {"ok": False, "train": [], "heldout": [], "train_sessions": [], "heldout_sessions": []}
    if holdout_sessions is None:
        n_hold = max(1, int(round(len(sessions) * holdout_fraction)))
        holdout_sessions = sessions[-n_hold:]
    hold_set = {int(s) for s in holdout_sessions}
    train_sessions = [s for s in sessions if s not in hold_set]
    train = [r for r in rows if int(r.get("session_i") or -1) in set(train_sessions)]
    held = [r for r in rows if int(r.get("session_i") or -1) in hold_set]
    # Integrity: no session id appears in both
    train_ids = {int(r["session_i"]) for r in train}
    hold_ids = {int(r["session_i"]) for r in held}
    leak = train_ids & hold_ids
    return {
        "ok": len(leak) == 0 and len(train) > 0 and len(held) > 0,
        "train": train,
        "heldout": held,
        "train_sessions": sorted(train_ids),
        "heldout_sessions": sorted(hold_ids),
        "leak_sessions": sorted(leak),
    }


def leave_one_session_out_stability(
    rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Fit alpha/beta leaving each session out; report beta/alpha dispersion."""
    sessions = sorted({int(r["session_i"]) for r in rows if r.get("session_i") is not None})
    folds: list[dict[str, Any]] = []
    for s in sessions:
        train = [r for r in rows if int(r["session_i"]) != s]
        xs = [float(r["eval_duration_s"]) for r in train if r.get("eval_duration_s") is not None]
        ys = [float(r["E_net_raw_j"]) for r in train if r.get("E_net_raw_j") is not None]
        # Align paired
        paired = [
            (float(r["eval_duration_s"]), float(r["E_net_raw_j"]))
            for r in train
            if r.get("eval_duration_s") is not None and r.get("E_net_raw_j") is not None
        ]
        if len(paired) < 2:
            continue
        xs, ys = zip(*paired)
        fit = fit_alpha_beta(list(xs), list(ys))
        folds.append(
            {
                "left_out_session": s,
                "alpha": fit.get("alpha"),
                "beta": fit.get("beta"),
                "r2": fit.get("r2"),
                "n_train": fit.get("n"),
            }
        )
    betas = [f["beta"] for f in folds if f.get("beta") is not None]
    alphas = [f["alpha"] for f in folds if f.get("alpha") is not None]
    return {
        "n_folds": len(folds),
        "folds": folds,
        "beta_mean": statistics.fmean(betas) if betas else None,
        "beta_std": statistics.pstdev(betas) if len(betas) > 1 else (0.0 if betas else None),
        "alpha_mean": statistics.fmean(alphas) if alphas else None,
        "alpha_std": statistics.pstdev(alphas) if len(alphas) > 1 else (0.0 if alphas else None),
        "beta_cv": (
            abs(statistics.pstdev(betas) / statistics.fmean(betas))
            if len(betas) > 1 and abs(statistics.fmean(betas)) > 1e-9
            else None
        ),
        "alpha_cv": (
            abs(statistics.pstdev(alphas) / statistics.fmean(alphas))
            if len(alphas) > 1 and abs(statistics.fmean(alphas)) > 1e-9
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Cell gates + decision ladder
# ---------------------------------------------------------------------------

HELD_OUT_MAE_J_MAX = 40.0
HELD_OUT_REL_ERR_MAX = 0.10
BETA_CV_MAX = 0.25


def evaluate_duration_cells(
    rows: Sequence[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Group by cell_id and apply evaluate_control_repeats with mean_from_E CV_P."""
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        cid = r.get("cell_id") or (r.get("cell") or {}).get("cell_id")
        if not cid:
            continue
        by_cell.setdefault(str(cid), []).append(r)
    reports: dict[str, dict[str, Any]] = {}
    for cid, group in by_cell.items():
        ev = evaluate_control_repeats(group, cv_p_primary="mean_from_E")
        # Annotate realized duration
        durs = [
            float(r["eval_duration_s"])
            for r in group
            if r.get("eval_duration_s") is not None
        ]
        ev["cell_id"] = cid
        ev["n_actions"] = len(group)
        ev["mu_eval_duration_s"] = statistics.fmean(durs) if durs else None
        ev["target_eval_s"] = group[0].get("target_eval_s")
        reports[cid] = ev
    return reports


def filter_gate_passing_rows(
    rows: Sequence[dict[str, Any]],
    cell_reports: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    passing = {
        cid
        for cid, rep in cell_reports.items()
        if rep.get("outcome") == "net_signature_repeatable"
    }
    return [
        r
        for r in rows
        if (r.get("cell_id") or (r.get("cell") or {}).get("cell_id")) in passing
        and r.get("eval_duration_s") is not None
        and r.get("E_net_raw_j") is not None
    ]


def classify_decision(
    *,
    cell_reports: dict[str, dict[str, Any]],
    heldout_metrics: dict[str, Any],
    stability: dict[str, Any],
    fit_train: dict[str, Any],
) -> dict[str, Any]:
    n_cells = len(cell_reports)
    n_pass = sum(
        1 for r in cell_reports.values() if r.get("outcome") == "net_signature_repeatable"
    )
    all_cells_repeatable = n_cells > 0 and n_pass == n_cells
    some_repeatable = n_pass > 0

    mae = heldout_metrics.get("mae_j")
    rel = heldout_metrics.get("mean_abs_rel_error")
    beta_cv = stability.get("beta_cv")
    heldout_ok = (
        mae is not None
        and rel is not None
        and float(mae) <= HELD_OUT_MAE_J_MAX
        and float(rel) <= HELD_OUT_REL_ERR_MAX
    )
    beta_stable = beta_cv is None or float(beta_cv) <= BETA_CV_MAX
    train_r2 = fit_train.get("r2")
    relationship_ok = (
        some_repeatable
        and train_r2 is not None
        and float(train_r2) >= 0.90
        and beta_stable
    )

    if not some_repeatable or not relationship_ok:
        decision = "ledger_descriptive_only"
        note = (
            "Validation failed repeatability and/or train relationship gates. "
            "Keep ledger descriptive only."
        )
    elif all_cells_repeatable and heldout_ok and beta_stable:
        decision = "predictor_candidate_for_separate_review"
        note = (
            "All duration cells repeatable and held-out accuracy within MAE/rel gates. "
            "Candidate for separate review only — no auto-admit, no Master routing."
        )
    else:
        decision = "cost_estimate_experiment_only"
        note = (
            "Repeatable relationship observed but held-out accuracy and/or cell coverage "
            "insufficient for predictor-candidate status. Cost-estimate experiment only."
        )

    return {
        "decision": decision,
        "note": note,
        "n_cells": n_cells,
        "n_pass_cells": n_pass,
        "all_cells_repeatable": all_cells_repeatable,
        "heldout_accuracy_ok": heldout_ok,
        "beta_stable": beta_stable,
        "relationship_ok": relationship_ok,
        "thresholds": {
            "heldout_mae_j_max": HELD_OUT_MAE_J_MAX,
            "heldout_rel_err_max": HELD_OUT_REL_ERR_MAX,
            "beta_cv_max": BETA_CV_MAX,
            "train_r2_min": 0.90,
        },
        "learning_admission_withheld": True,
        "auto_admit": False,
        "predictor_authorized": False,
        "master_routing_authorized": False,
    }


def evaluate_validation_campaign(
    rows: Sequence[dict[str, Any]],
    *,
    holdout_sessions: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Full offline evaluation of a completed duration-validation campaign."""
    cell_reports = evaluate_duration_cells(rows)
    gated = filter_gate_passing_rows(rows, cell_reports)

    split = session_holdout_split(gated, holdout_sessions=holdout_sessions)
    train = split.get("train") or []
    held = split.get("heldout") or []

    train_paired = [
        (float(r["eval_duration_s"]), float(r["E_net_raw_j"]))
        for r in train
        if r.get("eval_duration_s") is not None and r.get("E_net_raw_j") is not None
    ]
    fit = (
        fit_alpha_beta([p[0] for p in train_paired], [p[1] for p in train_paired])
        if train_paired
        else {"ok": False, "alpha": None, "beta": None, "r2": None, "n": 0}
    )

    preds = []
    held_metrics: dict[str, Any] = summarize_predictions([])
    if fit.get("ok") and fit.get("alpha") is not None and fit.get("beta") is not None:
        preds = predict_rows(held, float(fit["alpha"]), float(fit["beta"]))
        held_metrics = summarize_predictions(preds)

    stability = leave_one_session_out_stability(gated)
    decision = classify_decision(
        cell_reports=cell_reports,
        heldout_metrics=held_metrics,
        stability=stability,
        fit_train=fit,
    )

    # Intercept diagnostic
    alpha = fit.get("alpha")
    alpha_note = None
    if alpha is not None:
        if abs(float(alpha)) > 80.0:
            alpha_note = (
                "Large intercept — possible unmodeled fixed costs "
                "(startup / prompt-eval / measurement boundary)."
            )
        else:
            alpha_note = "Intercept magnitude within modest band."

    return {
        "ok": True,
        "n_actions": len(rows),
        "n_gated_actions": len(gated),
        "cell_reports": cell_reports,
        "split": {
            "ok": split.get("ok"),
            "train_sessions": split.get("train_sessions"),
            "heldout_sessions": split.get("heldout_sessions"),
            "n_train": len(train),
            "n_heldout": len(held),
            "leak_sessions": split.get("leak_sessions"),
        },
        "fit_train": fit,
        "heldout_predictions": preds,
        "heldout_metrics": held_metrics,
        "stability": stability,
        "alpha_diagnostic": {"alpha": alpha, "note": alpha_note},
        "decision": decision,
        "claim": (
            "On this hardware and fixed inference configuration, net action energy "
            "is predominantly determined by evaluation duration — prospective test."
        ),
        "learning_admission_withheld": True,
        "auto_admit": False,
        "predictor_authorized": False,
    }


def enrich_action_row(row: dict[str, Any], *, target_eval_s: float | None = None) -> dict[str, Any]:
    """Flatten infer.eval_duration_s onto the action row for offline analysis."""
    infer = row.get("infer") or {}
    out = dict(row)
    if out.get("eval_duration_s") is None:
        out["eval_duration_s"] = infer.get("eval_duration_s")
    if out.get("actual_eval_tokens") is None:
        out["actual_eval_tokens"] = infer.get("eval_count")
    if out.get("cell_id") is None:
        out["cell_id"] = (row.get("cell") or {}).get("cell_id")
    if target_eval_s is not None:
        out["target_eval_s"] = float(target_eval_s)
    return out
