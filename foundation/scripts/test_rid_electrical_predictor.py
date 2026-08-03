#!/usr/bin/env python3
"""Unit tests for rid_electrical_predictor.py (no plant run)."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_predictor import (  # noqa: E402
    ALPHA,
    BETA,
    DOMAIN_MAX_S,
    DOMAIN_MIN_S,
    HELD_OUT_RMSE_J,
    MAX_ABS_RESIDUAL_J,
    PLANT_CONFIG_ID,
    PREDICTOR_VERSION,
    predict_E_net,
    predict_with_error_scale,
)


def main() -> int:
    # In-domain prediction matches formula
    for t in [2.5, 3.0, 3.5, 4.0, 4.5]:
        r = predict_E_net(t)
        assert r["in_domain"] is True, f"expected in_domain for t={t}"
        assert r["predicted_E_net_j"] is not None
        expected = ALPHA + BETA * t
        assert abs(r["predicted_E_net_j"] - expected) < 1e-9, f"formula mismatch at t={t}"
        assert r["confidence"] == "empirical_3.7pct_rel_heldout"
        assert r["heldout_rmse_j"] == HELD_OUT_RMSE_J
        assert r["empirical_error_scale_j"] == HELD_OUT_RMSE_J
        assert r["max_abs_residual_j"] == MAX_ABS_RESIDUAL_J
        assert r["predictor_version"] == PREDICTOR_VERSION
        assert r["provenance"] == "eval_duration_validation_v1"

    # Interval is non-zero (derived from residuals, not invented zero)
    r = predict_E_net(3.0)
    assert r["heldout_rmse_j"] > 0.0

    # Authority fields are always False
    for t in [2.5, 3.0, 4.5, 0.5, 10.0]:
        r = predict_E_net(t)
        assert r["operational_authority"] is False
        assert r["master_routing_authorized"] is False
        assert r["auto_admit"] is False

    # Out-of-domain: below minimum
    for t in [0.0, 0.5, 1.0, 2.4, 2.499]:
        r = predict_E_net(t)
        assert r["predicted_E_net_j"] is None, f"expected None for t={t}"
        assert r["confidence"] == "out_of_validated_domain"
        assert r["in_domain"] is False

    # Out-of-domain: above maximum
    for t in [4.501, 5.0, 10.0, 100.0]:
        r = predict_E_net(t)
        assert r["predicted_E_net_j"] is None, f"expected None for t={t}"
        assert r["confidence"] == "out_of_validated_domain"
        assert r["in_domain"] is False

    # Boundary values are in-domain
    r_lo = predict_E_net(DOMAIN_MIN_S)
    r_hi = predict_E_net(DOMAIN_MAX_S)
    assert r_lo["in_domain"] is True
    assert r_hi["in_domain"] is True

    # Config mismatch guard
    r_mismatch = predict_E_net(3.0, plant_config_id="wrong_config")
    assert r_mismatch["predicted_E_net_j"] is None
    assert r_mismatch["confidence"] == "config_mismatch"
    assert r_mismatch["operational_authority"] is False

    # Correct config passes through
    r_ok = predict_E_net(3.0, plant_config_id=PLANT_CONFIG_ID)
    assert r_ok["predicted_E_net_j"] is not None
    assert r_ok["confidence"] == "empirical_3.7pct_rel_heldout"

    # predict_with_error_scale adds scale bounds
    r_iv = predict_with_error_scale(3.5)
    assert r_iv["error_scale_low_j"] is not None
    assert r_iv["error_scale_high_j"] is not None
    e = r_iv["predicted_E_net_j"]
    u = r_iv["heldout_rmse_j"]
    assert abs(r_iv["error_scale_low_j"] - (e - u)) < 1e-9
    assert abs(r_iv["error_scale_high_j"] - (e + u)) < 1e-9

    # predict_with_error_scale out-of-domain returns None bounds
    r_iv_ood = predict_with_error_scale(1.0)
    assert r_iv_ood["error_scale_low_j"] is None
    assert r_iv_ood["error_scale_high_j"] is None

    # Intercept note is present and non-empty
    r = predict_E_net(3.0)
    assert isinstance(r["intercept_note"], str) and len(r["intercept_note"]) > 10

    # Validated domain reported correctly
    assert r["validated_domain"] == [DOMAIN_MIN_S, DOMAIN_MAX_S]

    print("PASS test_rid_electrical_predictor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
