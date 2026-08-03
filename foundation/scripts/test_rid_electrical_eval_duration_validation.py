#!/usr/bin/env python3
"""Unit tests for eval_duration -> E_net validation (no plant run)."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_eval_duration_validation import (  # noqa: E402
    DURATION_TARGETS_S,
    build_session_orders,
    classify_decision,
    evaluate_validation_campaign,
    fit_alpha_beta,
    make_duration_cells,
    num_predict_for_target,
    predict_rows,
    rotation_coverage,
    session_holdout_split,
    summarize_predictions,
)


def _row(
    *,
    session_i: int,
    cell_id: str,
    eval_dur: float,
    e_net: float,
    e_gen: float | None = None,
    target: float | None = None,
    sigma: float = 4.0,
    dt: float | None = None,
) -> dict:
    if e_gen is None:
        e_gen = e_net + 150.0
    if dt is None:
        dt = eval_dur + 0.4
    return {
        "session_i": session_i,
        "order_i": 1,
        "cell_id": cell_id,
        "target_eval_s": target if target is not None else eval_dur,
        "num_predict": num_predict_for_target(eval_dur),
        "eval_duration_s": eval_dur,
        "E_net_raw_j": e_net,
        "E_net_j": e_net,
        "E_generate_j": e_gen,
        "P_mean_from_E_w": e_gen / dt,
        "P_peak_generate_w": e_gen / dt + 10,
        "delta_t_generate_s": dt,
        "n_generate_locked_samples": 30,
        "control_gates": {
            "settle_ok": True,
            "CV_P_idle_ok": True,
            "CV_P_idle": 0.04,
            "integration_wall_ratio": 1.0,
            "integration_wall_ratio_ok": True,
            "sigma_baseline_subtraction_est_j": sigma,
        },
    }


def _perfect_campaign(noise: float = 2.0) -> list[dict]:
    """5 sessions × 5 duration cells with E = 40 + 110*t (+tiny noise)."""
    cells = make_duration_cells()
    rows: list[dict] = []
    for s in range(1, 6):
        for c in cells:
            t = c.target_eval_s + (s - 3) * 0.01  # slight session jitter
            e = 40.0 + 110.0 * t + (s - 3) * noise * 0.1
            rows.append(
                _row(
                    session_i=s,
                    cell_id=c.cell_id,
                    eval_dur=t,
                    e_net=e,
                    target=c.target_eval_s,
                    sigma=3.0,
                )
            )
    return rows


def _noisy_heldout_campaign() -> list[dict]:
    """Train-like linear, but held-out sessions have large bias — weak accuracy."""
    cells = make_duration_cells()
    rows: list[dict] = []
    for s in range(1, 6):
        for c in cells:
            t = c.target_eval_s
            if s <= 3:
                e = 40.0 + 110.0 * t
            else:
                e = 40.0 + 110.0 * t + 120.0  # large held-out bias
            rows.append(
                _row(
                    session_i=s,
                    cell_id=c.cell_id,
                    eval_dur=t,
                    e_net=e,
                    target=c.target_eval_s,
                    sigma=3.0,
                )
            )
    return rows


def main() -> int:
    # Target mapping
    assert num_predict_for_target(2.5) == 258  # 2.5*103 rounded
    cells = make_duration_cells()
    assert len(cells) == len(DURATION_TARGETS_S)
    assert cells[0].num_predict == num_predict_for_target(2.5)

    # Rotation coverage
    orders = build_session_orders(cells, n_sessions=5)
    cov = rotation_coverage(orders)
    assert cov["ok"], cov
    assert cov["n_sessions"] == 5

    # Fit exact line
    xs = [2.5, 3.0, 3.5, 4.0, 4.5]
    ys = [40 + 110 * x for x in xs]
    fit = fit_alpha_beta(xs, ys)
    assert fit["ok"]
    assert abs(fit["alpha"] - 40.0) < 1e-6
    assert abs(fit["beta"] - 110.0) < 1e-6
    assert abs(fit["r2"] - 1.0) < 1e-9

    # Session holdout integrity
    rows = _perfect_campaign()
    split = session_holdout_split(rows, holdout_sessions=[4, 5])
    assert split["ok"]
    assert split["train_sessions"] == [1, 2, 3]
    assert split["heldout_sessions"] == [4, 5]
    assert not (set(split["train_sessions"]) & set(split["heldout_sessions"]))
    train_sids = {r["session_i"] for r in split["train"]}
    hold_sids = {r["session_i"] for r in split["heldout"]}
    assert train_sids.isdisjoint(hold_sids)

    # Predictions / metrics
    preds = predict_rows(split["heldout"], 40.0, 110.0)
    metrics = summarize_predictions(preds)
    assert metrics["n"] == 10
    assert metrics["mae_j"] is not None and metrics["mae_j"] < 5.0

    # Perfect campaign -> predictor candidate
    ev = evaluate_validation_campaign(rows, holdout_sessions=[4, 5])
    assert ev["split"]["ok"]
    assert ev["fit_train"]["ok"]
    assert abs(ev["fit_train"]["beta"] - 110.0) < 5.0
    dec = ev["decision"]["decision"]
    assert dec == "predictor_candidate_for_separate_review", ev["decision"]
    assert ev["auto_admit"] is False
    assert ev["learning_admission_withheld"] is True
    assert ev["predictor_authorized"] is False

    # Weak held-out accuracy -> cost_estimate_experiment_only
    noisy = _noisy_heldout_campaign()
    ev2 = evaluate_validation_campaign(noisy, holdout_sessions=[4, 5])
    assert ev2["decision"]["decision"] == "cost_estimate_experiment_only", ev2["decision"]

    # Gate failure -> ledger_descriptive_only
    bad_rows = [
        _row(
            session_i=1,
            cell_id="teval_2.5s_np258__warm_repeat",
            eval_dur=2.5,
            e_net=5.0,  # near floor — SNR fail
            sigma=20.0,
        )
        for _ in range(5)
    ]
    # Make CV fail / below resolution by near-zero net
    for i, r in enumerate(bad_rows):
        r["E_net_raw_j"] = 1.0 + i * 0.1
        r["E_net_j"] = r["E_net_raw_j"]
        r["session_i"] = i + 1
    # Need multiple cells for campaign structure — single unstable cell
    ev3 = evaluate_validation_campaign(bad_rows, holdout_sessions=[4, 5])
    # With few gated rows, relationship fails
    assert ev3["decision"]["decision"] == "ledger_descriptive_only", ev3["decision"]

    # classify_decision thresholds smoke
    fake_cells = {
        "a": {"outcome": "net_signature_repeatable"},
        "b": {"outcome": "net_signature_repeatable"},
    }
    d = classify_decision(
        cell_reports=fake_cells,
        heldout_metrics={"mae_j": 10.0, "mean_abs_rel_error": 0.05},
        stability={"beta_cv": 0.05},
        fit_train={"r2": 0.99},
    )
    assert d["decision"] == "predictor_candidate_for_separate_review"
    assert d["auto_admit"] is False

    print("PASS test_rid_electrical_eval_duration_validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
