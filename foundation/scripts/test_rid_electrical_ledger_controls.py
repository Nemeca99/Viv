#!/usr/bin/env python3
"""Unit tests for ledger controls v2 (no live Ollama)."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_ledger_controls import (  # noqa: E402
    CV_E_MAX,
    evaluate_control_repeats,
)


def _row(
    *,
    e_net: float,
    e_gen: float,
    peak: float,
    mean_from_e: float | None = None,
    n_samp: int = 12,
    sigma_est: float = 2.0,
) -> dict:
    return {
        "E_net_raw_j": e_net,
        "E_net_j": e_net if abs(e_net) >= 5.0 else None,
        "E_generate_j": e_gen,
        "P_peak_generate_w": peak,
        "P_mean_from_E_w": mean_from_e if mean_from_e is not None else e_gen / 2.0,
        "n_generate_locked_samples": n_samp,
        "control_gates": {
            "settle_ok": True,
            "CV_P_idle_ok": True,
            "integration_wall_ratio": 1.0,
            "integration_wall_ratio_ok": True,
            "sigma_baseline_subtraction_est_j": sigma_est,
        },
    }


def main() -> int:
    # High-SNR net-repeatable
    good = [
        _row(e_net=200.0 + i * 2.0, e_gen=400.0 + i, peak=160.0 + i, n_samp=20)
        for i in range(5)
    ]
    g = evaluate_control_repeats(good)
    assert g["outcome"] == "net_signature_repeatable", g
    assert g["net_attribution"] == "authoritative"
    assert g["CV_E"] is not None and g["CV_E"] <= CV_E_MAX
    assert g["SNR_net_ok"] is True

    # Low-SNR: gross OK, net below resolution (not unstable)
    short = [
        _row(
            e_net=v,
            e_gen=58.0 + i * 0.5,
            peak=100.0 + i * 5,
            mean_from_e=55.0 + i * 0.3,
            n_samp=5,
            sigma_est=3.0,
        )
        for i, v in enumerate([2.4, -5.7, 2.2, 1.8, 2.7])
    ]
    s = evaluate_control_repeats(short)
    assert s["outcome"] == "gross_signature_repeatable", s
    assert s["net_attribution"] == "below_resolution", s
    assert s["CV_E"] is None  # must not compute misleading CV
    assert s["SNR_net_ok"] is False

    # SNR OK (≈3.5) but CV_E≈0.29 > 0.20 → unstable (not below_resolution)
    unstable = [
        _row(e_net=v, e_gen=400.0 + i, peak=160.0, n_samp=20, sigma_est=10.0)
        for i, v in enumerate([130.0, 200.0, 270.0])
    ]
    u = evaluate_control_repeats(unstable)
    assert u["SNR_net_ok"] is True, u
    assert u["outcome"] == "unstable_signature", u
    assert u["net_attribution"] == "snr_ok_but_cv_failed", u

    print("PASS test_rid_electrical_ledger_controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
