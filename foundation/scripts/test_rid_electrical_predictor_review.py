#!/usr/bin/env python3
"""Tests for predictor separate review and hardening."""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_drift_check import compute_drift_summary  # noqa: E402
from lib.rid_electrical_predictor import (  # noqa: E402
    _AUTHORITY_FIELDS,
    predict_E_net,
    predict_with_error_scale,
)


def main() -> int:
    # Adversarial input handling
    for x in [float("nan"), float("inf"), float("-inf"), -0.1, "abc", "", None]:
        r = predict_E_net(x)  # type: ignore[arg-type]
        assert r["predicted_E_net_j"] is None
        assert r["confidence"] == "invalid_input"

    # Boundary floating behavior
    r1 = predict_E_net(2.4999)
    assert r1["confidence"] == "out_of_validated_domain"
    r2 = predict_E_net(2.5)
    assert r2["in_domain"] is True
    r3 = predict_E_net(2.5 - 1e-15)
    # floating precision edge should not crash and stays deterministic
    assert r3["confidence"] in {"empirical_3.7pct_rel_heldout", "out_of_validated_domain"}

    # Forged config
    rf = predict_E_net(3.0, plant_config_id="forged")
    assert rf["predicted_E_net_j"] is None
    assert rf["confidence"] == "config_mismatch"

    # Authority immutable in all branches
    for r in [predict_E_net(3.0), predict_E_net(10.0), predict_E_net("abc")]:
        for k, v in _AUTHORITY_FIELDS.items():
            assert r[k] is v

    # Uncertainty naming
    r = predict_E_net(3.0)
    assert "heldout_rmse_j" in r
    assert "empirical_error_scale_j" in r
    assert "prediction_interval_j" not in r
    rv = predict_with_error_scale(3.0)
    assert rv["error_scale_low_j"] is not None and rv["error_scale_high_j"] is not None

    # Drift alert logic
    quiet = compute_drift_summary([{"residual_j": 5.0}, {"residual_j": -6.0}, {"residual_j": 4.0}])
    noisy = compute_drift_summary([{"residual_j": 60.0}, {"residual_j": -45.0}, {"residual_j": 55.0}])
    assert quiet["drift_alert"] is False
    assert noisy["drift_alert"] is True
    assert math.isfinite(float(noisy["drift_alert_threshold_j"]))

    # Review runner verdict
    proc = subprocess.run(
        [r"L:/Continue/.venv/Scripts/python.exe", str(FOUNDATION / "scripts" / "rid_electrical_predictor_review.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    print("PASS test_rid_electrical_predictor_review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

