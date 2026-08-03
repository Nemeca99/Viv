#!/usr/bin/env python3
"""Lock the calibrated eval_duration predictor from validation artifact.

Reads eval_duration_validation_latest.json, verifies coefficients match the
locked predictor module constants, writes PREDICTOR_LOCKED_EVAL_DURATION_V1.json,
and smoke-tests a few predictions.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_lock_predictor.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_policy import policy_stamp  # noqa: E402
from lib.rid_electrical_predictor import (  # noqa: E402
    ALPHA,
    BETA,
    DOMAIN_MAX_S,
    DOMAIN_MIN_S,
    HELD_OUT_MU_RESIDUAL_J,
    HELD_OUT_RMSE_J,
    HELD_OUT_SIGMA_RESIDUAL_J,
    HELD_OUT_MEAN_ABS_REL_ERR,
    INTERCEPT_NOTE,
    MAX_ABS_RESIDUAL_J,
    PLANT_CONFIG_ID,
    PREDICTOR_VERSION,
    PROVENANCE,
    VALIDATED_DOMAIN,
    predict_E_net,
    predict_with_error_scale,
)

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
VALIDATION_JSON = OUT / "eval_duration_validation_latest.json"
LOCK_PATH = OUT / "PREDICTOR_LOCKED_EVAL_DURATION_V1.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    if not VALIDATION_JSON.exists():
        print(json.dumps({"error": "eval_duration_validation_latest.json not found"}))
        return 1

    val = json.loads(VALIDATION_JSON.read_text(encoding="utf-8"))
    ev = val.get("evaluation") or {}
    fit = ev.get("fit_train") or {}
    held = ev.get("heldout_metrics") or {}
    stab = ev.get("stability") or {}
    decision_block = ev.get("decision") or {}

    # Verify locked constants match artifact (tolerance for float repr)
    artifact_alpha = fit.get("alpha")
    artifact_beta = fit.get("beta")
    tol = 0.01
    if artifact_alpha is None or abs(float(artifact_alpha) - ALPHA) > tol:
        print(
            json.dumps(
                {
                    "error": "alpha_mismatch",
                    "artifact": artifact_alpha,
                    "locked": ALPHA,
                }
            )
        )
        return 1
    if artifact_beta is None or abs(float(artifact_beta) - BETA) > tol:
        print(
            json.dumps(
                {
                    "error": "beta_mismatch",
                    "artifact": artifact_beta,
                    "locked": BETA,
                }
            )
        )
        return 1

    # Smoke-test predictions at domain boundaries and midpoint
    smoke = []
    for t in [DOMAIN_MIN_S, 3.0, 3.5, DOMAIN_MAX_S]:
        r = predict_with_error_scale(t)
        smoke.append(r)
        assert r["in_domain"] is True
        assert r["predicted_E_net_j"] is not None
        assert r["operational_authority"] is False
        assert r["master_routing_authorized"] is False
        assert r["auto_admit"] is False
        assert r["heldout_rmse_j"] == HELD_OUT_RMSE_J

    # Out-of-domain guards
    for t in [0.5, 1.0, 2.4, 4.6, 10.0]:
        r = predict_E_net(t)
        assert r["predicted_E_net_j"] is None, f"expected None for t={t}"
        assert r["confidence"] == "out_of_validated_domain"
        assert r["operational_authority"] is False

    # Config mismatch guard
    r_mismatch = predict_E_net(3.0, plant_config_id="wrong_config")
    assert r_mismatch["predicted_E_net_j"] is None
    assert r_mismatch["confidence"] == "config_mismatch"

    lock = {
        "ok": True,
        "at": _utc(),
        "predictor_version": PREDICTOR_VERSION,
        "provenance": PROVENANCE,
        "source_validation_artifact": str(VALIDATION_JSON).replace("\\", "/"),
        "coefficients": {
            "alpha_j": ALPHA,
            "beta_j_per_s": BETA,
            "formula": "E_net_hat = alpha + beta * eval_duration_s",
            "intercept_note": INTERCEPT_NOTE,
        },
        "domain": {
            "min_eval_duration_s": DOMAIN_MIN_S,
            "max_eval_duration_s": DOMAIN_MAX_S,
            "out_of_domain_response": "out_of_validated_domain",
            "below_resolution_rule": "use E_generate_gross; E_net=null/below_resolution",
        },
        "uncertainty": {
            "held_out_rmse_j": HELD_OUT_RMSE_J,
            "held_out_sigma_residual_j": HELD_OUT_SIGMA_RESIDUAL_J,
            "held_out_mu_residual_j": HELD_OUT_MU_RESIDUAL_J,
            "max_abs_residual_j": MAX_ABS_RESIDUAL_J,
            "mean_abs_rel_error": HELD_OUT_MEAN_ABS_REL_ERR,
            "coverage_note": "heldout_rmse_j is RMSE from held-out sessions 4-5; not a validated prediction interval.",
        },
        "stability": {
            "beta_cv": stab.get("beta_cv"),
            "alpha_cv": stab.get("alpha_cv"),
            "beta_mean": stab.get("beta_mean"),
            "beta_std": stab.get("beta_std"),
            "alpha_mean": stab.get("alpha_mean"),
            "alpha_std": stab.get("alpha_std"),
            "n_folds": stab.get("n_folds"),
        },
        "plant_configuration": {
            "plant_config_id": PLANT_CONFIG_ID,
            "model": "viv-voice-qwen",
            "residency": "warm_repeat",
            "baseline_recipe": "settled_8s_window",
            "telemetry_cadence_s": 0.1,
            "note": "Any material change to model/quantization/hardware/executor/baseline "
                    "recipe/telemetry cadence invalidates this calibration. "
                    "Caller must pass matching plant_config_id or accept unchecked confidence.",
        },
        "train_evidence": {
            "n_train_rows": fit.get("n"),
            "train_r2": fit.get("r2"),
            "train_sessions": (ev.get("split") or {}).get("train_sessions"),
            "heldout_sessions": (ev.get("split") or {}).get("heldout_sessions"),
            "n_heldout_rows": (ev.get("split") or {}).get("n_heldout"),
        },
        "decision_ladder": {
            "campaign_decision": decision_block.get("decision"),
            "all_cells_repeatable": decision_block.get("all_cells_repeatable"),
            "heldout_accuracy_ok": decision_block.get("heldout_accuracy_ok"),
            "beta_stable": decision_block.get("beta_stable"),
            "note": decision_block.get("note"),
        },
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "predictor_blocked_from_operational_use": True,
            "learning_admission_withheld": True,
            "narrow_accounting_estimate_only": True,
            "status": "predictor_candidate_for_separate_review",
        },
        "smoke_predictions": [
            {
                "eval_duration_s": r["eval_duration_s"],
                "predicted_E_net_j": r.get("predicted_E_net_j"),
                "error_scale_low_j": r.get("error_scale_low_j"),
                "error_scale_high_j": r.get("error_scale_high_j"),
                "confidence": r["confidence"],
            }
            for r in smoke
        ],
        "policy": policy_stamp(),
    }

    LOCK_PATH.write_text(json.dumps(lock, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "predictor_version": PREDICTOR_VERSION,
                "alpha": ALPHA,
                "beta": BETA,
                "domain": VALIDATED_DOMAIN,
                "held_out_rmse_j": HELD_OUT_RMSE_J,
                "smoke_pass": True,
                "artifact": str(LOCK_PATH).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
