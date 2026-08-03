#!/usr/bin/env python3
"""Unit tests for token matrix v2 (no live Ollama)."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_token_matrix import (  # noqa: E402
    ADMISSION_NUM_PREDICT,
    SESSION_ORDERS,
    classify_milestone,
    evaluate_separability,
    evaluate_token_matrix,
    rotation_coverage,
)


def _row(
    *,
    cell_id: str,
    num_predict: int,
    e_net: float,
    e_gen: float,
    mean_p: float,
    peak: float = 200.0,
    n_samp: int = 25,
    dt: float = 3.0,
    sigma_est: float = 5.0,
) -> dict:
    return {
        "cell": {
            "cell_id": cell_id,
            "num_predict": num_predict,
            "residency": "warm_repeat",
        },
        "E_net_raw_j": e_net,
        "E_net_j": e_net,
        "E_generate_j": e_gen,
        "P_mean_from_E_w": mean_p,
        "P_peak_generate_w": peak,
        "n_generate_locked_samples": n_samp,
        "delta_t_generate_s": dt,
        "control_gates": {
            "settle_ok": True,
            "CV_P_idle_ok": True,
            "integration_wall_ratio": 1.0,
            "integration_wall_ratio_ok": True,
            "sigma_baseline_subtraction_est_j": sigma_est,
        },
    }


def _stable_cell(cell_id: str, np: int, mu: float, n: int = 5) -> list[dict]:
    return [
        _row(
            cell_id=cell_id,
            num_predict=np,
            e_net=mu + (i - n // 2) * 2.0,
            e_gen=mu * 1.5 + i,
            mean_p=150.0 + i * 0.2,
            peak=220.0 + i,
        )
        for i in range(n)
    ]


def main() -> int:
    cov = rotation_coverage()
    assert cov["ok"], cov
    assert cov["n_sessions"] == 5
    for np in ADMISSION_NUM_PREDICT:
        assert cov["counts"][np] == 5, cov
    # each session is a permutation of admission set
    for order in SESSION_ORDERS:
        assert sorted(order) == sorted(ADMISSION_NUM_PREDICT)

    # Separable rising curve → token_cost_curve_reviewable
    rows = []
    rows += _stable_cell("tokens_np256__warm_repeat", 256, 280.0)
    rows += _stable_cell("tokens_np384__warm_repeat", 384, 420.0)
    rows += _stable_cell("tokens_np512__warm_repeat", 512, 560.0)
    # forensic must not affect admission decision
    rows += _stable_cell("tokens_np768__warm_forensic", 768, 700.0, n=3)

    summary = evaluate_token_matrix(
        [r for r in rows if not r["cell"]["cell_id"].endswith("forensic")],
        forensic_rows=[r for r in rows if r["cell"]["cell_id"].endswith("forensic")],
    )
    ms = summary["milestone"]
    assert ms["campaign_decision"] == "token_cost_curve_reviewable", ms
    assert ms["auto_admit"] is False
    assert summary["separability"]["all_pairs_separable"] is True

    # Overlap → not explanatory
    overlap = []
    overlap += _stable_cell("tokens_np256__warm_repeat", 256, 300.0)
    overlap += _stable_cell("tokens_np384__warm_repeat", 384, 305.0)
    overlap += _stable_cell("tokens_np512__warm_repeat", 512, 302.0)
    s2 = evaluate_token_matrix(overlap)
    assert s2["milestone"]["campaign_decision"] in {
        "accounting_stable_tokens_not_explanatory",
        "ledger_descriptive_only",
    }, s2["milestone"]

    # Mixed unstable
    mixed = _stable_cell("tokens_np256__warm_repeat", 256, 280.0)
    # make 384 unstable via high E_net scatter with still high SNR
    for i, v in enumerate([100.0, 300.0, 500.0, 280.0, 320.0]):
        mixed.append(
            _row(
                cell_id="tokens_np384__warm_repeat",
                num_predict=384,
                e_net=v,
                e_gen=600.0 + i,
                mean_p=160.0,
                sigma_est=20.0,
            )
        )
    mixed += _stable_cell("tokens_np512__warm_repeat", 512, 560.0)
    s3 = evaluate_token_matrix(mixed)
    assert s3["milestone"]["campaign_decision"] == "investigate_unstable_cells", s3[
        "milestone"
    ]

    # Separability helper unit
    reports = {
        "tokens_np256__warm_repeat": {
            "outcome": "net_signature_repeatable",
            "mu_E_net_raw_j": 100.0,
            "sigma_E_net_raw_j": 5.0,
            "n_usable": 5,
        },
        "tokens_np512__warm_repeat": {
            "outcome": "net_signature_repeatable",
            "mu_E_net_raw_j": 200.0,
            "sigma_E_net_raw_j": 5.0,
            "n_usable": 5,
        },
    }
    sep = evaluate_separability(reports)
    assert sep["all_pairs_separable"] is True, sep

    print("PASS test_rid_electrical_token_matrix")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
