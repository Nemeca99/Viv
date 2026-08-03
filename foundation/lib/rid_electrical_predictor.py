#!/usr/bin/env python3
"""Narrow accounting predictor: E_net ~= alpha + beta * eval_duration_s.

Version-locked, domain-guarded, fail-closed.

Valid ONLY within [DOMAIN_MIN_S, DOMAIN_MAX_S] on the exact tested plant
configuration. Outside that range or on a different config, returns null
with an explicit confidence label.

No operational authority. No Master routing. No auto-admit.
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Calibration — locked from eval_duration_validation_v1 (sessions 1-3 train)
# ---------------------------------------------------------------------------
PREDICTOR_VERSION = "eval_duration_v1"

# Fit coefficients (OLS, train sessions 1-3, n=15 paired rows)
ALPHA = -160.03454641296582   # J — empirical intercept; NOT a physical fixed-cost
BETA = 183.2363034039116       # J/s

# Validated domain (must match plant run range exactly)
DOMAIN_MIN_S = 2.5
DOMAIN_MAX_S = 4.5

# Uncertainty from held-out sessions 4-5 (n=10 predictions)
HELD_OUT_RMSE_J = 19.296223203691802
HELD_OUT_SIGMA_RESIDUAL_J = 18.529852037176887
HELD_OUT_MU_RESIDUAL_J = 5.384126057869144   # slight positive bias
MAX_ABS_RESIDUAL_J = 30.060858497380536
HELD_OUT_MEAN_ABS_REL_ERR = 0.03661574848517671

# Plant configuration this calibration is locked to
PLANT_CONFIG_ID = (
    "viv-voice-qwen_warm-repeat_settled-baseline_eval-dur-v1"
    "_hardware=local-pc_telemetry-cadence=0.1s"
)

INTERCEPT_NOTE = (
    "Alpha is an empirically fitted coefficient useful within [2.5, 4.5] s. "
    "It is NOT a physical decomposition of fixed session startup or prompt-eval costs. "
    "A negative alpha likely reflects the restricted fit range, idle-baseline "
    "subtraction, timing boundaries, or an omitted correlated phase."
)

PROVENANCE = "eval_duration_validation_v1"

VALIDATED_DOMAIN = [DOMAIN_MIN_S, DOMAIN_MAX_S]

_AUTHORITY_FIELDS: dict[str, bool] = {
    "operational_authority": False,
    "master_routing_authorized": False,
    "auto_admit": False,
}

COVERAGE_NOTE = (
    "RMSE over n=10 held-out predictions. Not a validated frequentist "
    "prediction interval. For worst-case bound see max_abs_residual_j."
)


def _sanitize_duration(t: float) -> str | None:
    """Return error label for unusable duration, else None."""
    if math.isnan(t) or math.isinf(t) or t < 0:
        return "invalid_input"
    return None


def predict_E_net(
    eval_duration_s: float,
    *,
    plant_config_id: str | None = None,
) -> dict[str, Any]:
    """Return a domain-guarded energy accounting estimate.

    Parameters
    ----------
    eval_duration_s:
        Measured Ollama eval_duration for the action (seconds).
    plant_config_id:
        Optional caller-supplied config string. If provided and does not match
        PLANT_CONFIG_ID, prediction is withheld with confidence='config_mismatch'.

    Returns
    -------
    dict with keys:
        predicted_E_net_j       float | None
        heldout_rmse_j          float  (RMSE from held-out residuals)
        empirical_error_scale_j float  (alias of heldout_rmse_j)
        max_abs_residual_j      float  (worst-case observed)
        coverage_note           str
        eval_duration_s         float
        validated_domain        [float, float]
        in_domain               bool
        plant_configuration_id  str
        confidence              str
        provenance              str
        predictor_version       str
        intercept_note          str
        operational_authority   bool  always False (hardcoded)
        master_routing_authorized bool always False (hardcoded)
        auto_admit              bool  always False (hardcoded)
    """
    try:
        t = float(eval_duration_s)
    except (TypeError, ValueError):
        return {
            "predicted_E_net_j": None,
            "heldout_rmse_j": HELD_OUT_RMSE_J,
            "empirical_error_scale_j": HELD_OUT_RMSE_J,
            "max_abs_residual_j": MAX_ABS_RESIDUAL_J,
            "coverage_note": COVERAGE_NOTE,
            "eval_duration_s": None,
            "validated_domain": VALIDATED_DOMAIN,
            "in_domain": False,
            "plant_configuration_id": PLANT_CONFIG_ID,
            "confidence": "invalid_input",
            "provenance": PROVENANCE,
            "predictor_version": PREDICTOR_VERSION,
            "intercept_note": INTERCEPT_NOTE,
            **_AUTHORITY_FIELDS,
        }
    bad = _sanitize_duration(t)
    if bad is not None:
        return {
            "predicted_E_net_j": None,
            "heldout_rmse_j": HELD_OUT_RMSE_J,
            "empirical_error_scale_j": HELD_OUT_RMSE_J,
            "max_abs_residual_j": MAX_ABS_RESIDUAL_J,
            "coverage_note": COVERAGE_NOTE,
            "eval_duration_s": t,
            "validated_domain": VALIDATED_DOMAIN,
            "in_domain": False,
            "plant_configuration_id": PLANT_CONFIG_ID,
            "confidence": bad,
            "provenance": PROVENANCE,
            "predictor_version": PREDICTOR_VERSION,
            "intercept_note": INTERCEPT_NOTE,
            **_AUTHORITY_FIELDS,
        }
    in_domain = DOMAIN_MIN_S <= t <= DOMAIN_MAX_S

    # Config guard
    if plant_config_id is not None and str(plant_config_id) != PLANT_CONFIG_ID:
        return {
            "predicted_E_net_j": None,
            "heldout_rmse_j": HELD_OUT_RMSE_J,
            "empirical_error_scale_j": HELD_OUT_RMSE_J,
            "max_abs_residual_j": MAX_ABS_RESIDUAL_J,
            "coverage_note": COVERAGE_NOTE,
            "eval_duration_s": t,
            "validated_domain": VALIDATED_DOMAIN,
            "in_domain": in_domain,
            "plant_configuration_id": PLANT_CONFIG_ID,
            "confidence": "config_mismatch",
            "provenance": PROVENANCE,
            "predictor_version": PREDICTOR_VERSION,
            "intercept_note": INTERCEPT_NOTE,
            **_AUTHORITY_FIELDS,
        }

    # Domain guard
    if not in_domain:
        return {
            "predicted_E_net_j": None,
            "heldout_rmse_j": HELD_OUT_RMSE_J,
            "empirical_error_scale_j": HELD_OUT_RMSE_J,
            "max_abs_residual_j": MAX_ABS_RESIDUAL_J,
            "coverage_note": COVERAGE_NOTE,
            "eval_duration_s": t,
            "validated_domain": VALIDATED_DOMAIN,
            "in_domain": False,
            "plant_configuration_id": PLANT_CONFIG_ID,
            "confidence": "out_of_validated_domain",
            "provenance": PROVENANCE,
            "predictor_version": PREDICTOR_VERSION,
            "intercept_note": INTERCEPT_NOTE,
            **_AUTHORITY_FIELDS,
        }

    predicted = ALPHA + BETA * t

    return {
        "predicted_E_net_j": predicted,
        "heldout_rmse_j": HELD_OUT_RMSE_J,
        "empirical_error_scale_j": HELD_OUT_RMSE_J,
        "max_abs_residual_j": MAX_ABS_RESIDUAL_J,
        "coverage_note": COVERAGE_NOTE,
        "eval_duration_s": t,
        "validated_domain": VALIDATED_DOMAIN,
        "in_domain": True,
        "plant_configuration_id": PLANT_CONFIG_ID,
        "confidence": "empirical_3.7pct_rel_heldout",
        "provenance": PROVENANCE,
        "predictor_version": PREDICTOR_VERSION,
        "intercept_note": INTERCEPT_NOTE,
        **_AUTHORITY_FIELDS,
    }


def predict_with_error_scale(eval_duration_s: float) -> dict[str, Any]:
    """Return prediction with symmetric RMSE-scaled bounds (not coverage-validated)."""
    r = predict_E_net(float(eval_duration_s))
    e = r.get("predicted_E_net_j")
    u = float(r["heldout_rmse_j"])
    return {
        **r,
        "error_scale_low_j": (e - u) if e is not None else None,
        "error_scale_high_j": (e + u) if e is not None else None,
    }
