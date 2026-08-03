#!/usr/bin/env python3
"""Unit tests for controlled ledger campaign CV gates (no live Ollama)."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_ledger_campaign import (  # noqa: E402
    CV_E_MAX,
    CellSpec,
    campaign_matrix,
    evaluate_cell_repeatability,
    evaluate_learning_admission,
)


def main() -> int:
    cells_smoke = campaign_matrix(smoke=True)
    assert len(cells_smoke) == 3
    cells = campaign_matrix(smoke=False)
    assert len(cells) >= 5
    assert all(isinstance(c, CellSpec) for c in cells)
    factors = {c.factor for c in cells}
    assert "tokens" in factors and "executor" in factors

    unstable = [
        {"confidence": "valid", "E_net_j": 1000.0, "P_peak_w": 150.0},
        {"confidence": "valid", "E_net_j": 3000.0, "P_peak_w": 200.0},
        {"confidence": "valid", "E_net_j": 5000.0, "P_peak_w": 250.0},
    ]
    u = evaluate_cell_repeatability(unstable)
    assert u["outcome"] == "unstable_signature"
    assert u["CV_E"] is not None and u["CV_E"] > CV_E_MAX

    stable = [
        {"confidence": "valid", "E_net_j": 2000.0, "P_peak_w": 160.0},
        {"confidence": "valid", "E_net_j": 2100.0, "P_peak_w": 165.0},
        {"confidence": "valid", "E_net_j": 2050.0, "P_peak_w": 162.0},
    ]
    s = evaluate_cell_repeatability(stable)
    assert s["outcome"] == "repeatable_signature"

    insuff = evaluate_cell_repeatability(stable[:1])
    assert insuff["outcome"] == "insufficient_evidence"

    long_cell = {
        **s,
        "mu_E_net_j": 5000.0,
        "sigma_E_net_j": 50.0,
        "n_valid": 3,
        "outcome": "repeatable_signature",
        "repeatable": True,
    }
    short_cell = {
        **s,
        "mu_E_net_j": 2000.0,
        "sigma_E_net_j": 40.0,
        "n_valid": 3,
        "outcome": "repeatable_signature",
        "repeatable": True,
    }
    adm = evaluate_learning_admission(
        {
            "tokens__tokens_short": short_cell,
            "tokens__tokens_long": long_cell,
        }
    )
    assert adm["auto_admit"] is False
    assert adm["learning_admission_granted"] is False
    assert adm["campaign_decision"] == "predictor_dataset_candidate"
    assert "tokens" in adm["separable_factors"]

    # Repeatable but not separable
    twin = {
        **s,
        "mu_E_net_j": 2000.0,
        "sigma_E_net_j": 100.0,
        "n_valid": 3,
        "outcome": "repeatable_signature",
        "repeatable": True,
    }
    adm2 = evaluate_learning_admission(
        {"tokens__a": twin, "tokens__b": {**twin, "mu_E_net_j": 2010.0}}
    )
    assert adm2["campaign_decision"] == "accounting_ledger_only"

    print("PASS test_rid_electrical_ledger_campaign")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
