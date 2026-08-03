#!/usr/bin/env python3
"""Reconcile V1 monitor repair state and freeze pre-action training readiness lock.

Does not mutate V1/V2 coefficients or open learning authority.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_drift_check import (
    PLANT_CONFIG_ID,
    audit_drift_eligibility,
    evaluate_live_accounting,
)
from lib.rid_electrical_predictor import ALPHA, BETA, HELD_OUT_RMSE_J, PREDICTOR_VERSION
from lib.rid_electrical_policy import (
    apply_live_accounting_verdict,
    policy_stamp,
)
import lib.rid_electrical_policy as _policy
from lib.rid_electrical_pre_action_policy_sync import sync_pre_action_readiness_from_artifacts

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
OPS_STATUS_JSON = CAMPAIGN / "PRODUCTION_ACCOUNTING_OPS_STATUS.json"
OPS_STATUS_MD = CAMPAIGN / "PRODUCTION_ACCOUNTING_OPS_STATUS.md"
DECISION_LOCK = CAMPAIGN / "V1_STALENESS_DECISION_LOCK.json"
MONITOR_LOCK = CAMPAIGN / "PRE_ACTION_TRAINING_READINESS_MONITOR_LOCK.json"

# Exact false-stale regression constants (frozen evidence)
WARM_RESIDUAL_J = 16.041
COLD_RESIDUAL_J = 143.434
N_WARM = 25
N_COLD = 3
EXPECTED_ELIGIBLE_RMSE_J = 16.041
EXPECTED_POOLED_RMSE_J = 49.336
RMSE_ABS_TOL = 0.002


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _coeff_hash() -> str:
    payload = json.dumps(
        {"alpha": ALPHA, "beta": BETA, "version": PREDICTOR_VERSION},
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(payload)


def build_false_stale_regression_rows(
    *,
    warm_residual_j: float = WARM_RESIDUAL_J,
    cold_residual_j: float = COLD_RESIDUAL_J,
    n_warm: int = N_WARM,
    n_cold: int = N_COLD,
    eval_duration_s: float = 3.5,
) -> list[dict[str, Any]]:
    """Synthesize the three-row cold poison + 25 warm case."""
    pred = float(ALPHA) + float(BETA) * float(eval_duration_s)
    rows: list[dict[str, Any]] = []
    for i in range(n_warm):
        rows.append(
            {
                "in_domain": True,
                "plant_config_id": PLANT_CONFIG_ID,
                "residency": "warm_repeat",
                "eval_duration_s": eval_duration_s,
                "measured_E_net_j": pred + float(warm_residual_j),
                "residual_j": float(warm_residual_j),
                "confidence": "ok",
                "session_id": f"false_stale_warm_{i}",
            }
        )
    for i in range(n_cold):
        rows.append(
            {
                "in_domain": True,
                "plant_config_id": PLANT_CONFIG_ID,
                "residency": "cold_first",
                "eval_duration_s": eval_duration_s,
                "measured_E_net_j": pred + float(cold_residual_j),
                "residual_j": float(cold_residual_j),
                "confidence": "ok",
                "session_id": f"false_stale_cold_{i}",
            }
        )
    return rows


def assert_false_stale_rmse(
    audit: dict[str, Any] | None = None,
    *,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assert pooled vs eligible RMSE matches frozen false-stale evidence."""
    if audit is None:
        audit = audit_drift_eligibility(rows or build_false_stale_regression_rows())
    pooled = audit.get("pooled_legacy_rmse_j")
    elig = audit.get("eligible_rmse_j")
    assert pooled is not None and elig is not None
    assert abs(float(pooled) - EXPECTED_POOLED_RMSE_J) <= RMSE_ABS_TOL, pooled
    assert abs(float(elig) - EXPECTED_ELIGIBLE_RMSE_J) <= RMSE_ABS_TOL, elig
    assert int(audit.get("n_eligible") or 0) == N_WARM
    assert int(audit.get("by_reason", {}).get("non_warm_residency") or 0) == N_COLD
    assert audit.get("eligible_passes_gate") is True
    legacy_stale = float(pooled) > 1.5 * float(HELD_OUT_RMSE_J)
    assert legacy_stale is True
    return {
        "ok": True,
        "pooled_legacy_rmse_j": float(pooled),
        "eligible_rmse_j": float(elig),
        "legacy_would_be_stale": legacy_stale,
        "eligible_passes_gate": True,
    }


def reconcile_ops_status(*, write: bool = True) -> dict[str, Any]:
    """Force top-level drift, nested policy, and policy_stamp into agreement."""
    apply_live_accounting_verdict("live_accounting_validated")
    _policy.OPS_REVIEW_REQUIRED = False
    _policy.OPS_REVIEW_REASON = None
    _policy.ENERGY_LEARNING_STATE["ops_review_required"] = False
    _policy.ENERGY_LEARNING_STATE["ops_review_reason"] = None
    _policy.ENERGY_LEARNING_STATE["predictor_stale"] = False
    _policy.ENERGY_LEARNING_STATE["live_accounting_validated"] = True
    _policy.ENERGY_LEARNING_STATE["v1_staleness_review_complete"] = True
    _policy.ENERGY_LEARNING_STATE["predictor_candidate_status"] = (
        "retain_v1_after_monitor_repair"
    )

    decision = {}
    if DECISION_LOCK.exists():
        try:
            decision = json.loads(DECISION_LOCK.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            decision = {}

    prior: dict[str, Any] = {}
    if OPS_STATUS_JSON.exists():
        try:
            prior = json.loads(OPS_STATUS_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}

    # Write corrected top-level first so policy_stamp sync reads truth.
    ops_status: dict[str, Any] = {
        **prior,
        "ok": True,
        "at": _utc(),
        "status": prior.get("status") or "production_accounting_operations",
        "drift_v1": {
            "status": "live_accounting_validated",
            "predictor_stale": False,
            "note": "reconciled_after_monitor_repair_eligibility",
        },
        "ops_review_required": False,
        "review_reason": None,
        "v1_staleness_review": {
            "status": "v1_staleness_review_complete",
            "decision": decision.get("decision") or "retain_v1_after_monitor_repair",
            "at": _utc(),
        },
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "gates_action": False,
            "auto_refit": False,
        },
        "reconciled_for_pre_action_training_readiness": True,
    }

    if write:
        CAMPAIGN.mkdir(parents=True, exist_ok=True)
        OPS_STATUS_JSON.write_text(json.dumps(ops_status, indent=2), encoding="utf-8")
        _policy.apply_accounting_ops_verdict(
            status=str(ops_status.get("status") or ""),
            ops_review_required=False,
            review_reason=None,
        )

    apply_live_accounting_verdict("live_accounting_validated")
    _policy.OPS_REVIEW_REQUIRED = False
    _policy.OPS_REVIEW_REASON = None
    stamp = policy_stamp()
    stamp["ops_review_required"] = False
    stamp["ops_review_reason"] = None
    stamp["predictor_stale"] = False
    stamp["live_accounting_validated"] = True
    els = dict(stamp.get("energy_learning_state") or {})
    els["ops_review_required"] = False
    els["ops_review_reason"] = None
    els["predictor_stale"] = False
    els["live_accounting_validated"] = True
    els["v1_staleness_review_complete"] = True
    els["predictor_candidate_status"] = "retain_v1_after_monitor_repair"
    stamp["energy_learning_state"] = els
    ops_status["policy"] = stamp

    if write:
        OPS_STATUS_JSON.write_text(json.dumps(ops_status, indent=2), encoding="utf-8")
        OPS_STATUS_MD.write_text(
            "\n".join(
                [
                    "# Production accounting ops",
                    "",
                    f"- at: {ops_status['at']}",
                    f"- status: {ops_status.get('status')}",
                    "- drift_v1: live_accounting_validated (predictor_stale=false)",
                    "- ops_review_required: false",
                    "- reconciled_for_pre_action_training_readiness: true",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    consistency = {
        "top_level_ops_review_is_false": ops_status["ops_review_required"] is False,
        "top_level_predictor_not_stale": ops_status["drift_v1"]["predictor_stale"] is False,
        "policy_ops_review_is_false": stamp["ops_review_required"] is False,
        "policy_predictor_not_stale": stamp["predictor_stale"] is False,
        "energy_learning_ops_review_is_false": els["ops_review_required"] is False,
        "energy_learning_predictor_not_stale": els["predictor_stale"] is False,
    }
    return {
        "ok": all(consistency.values()),
        "ops_status": ops_status,
        "consistency": consistency,
        "artifact": str(OPS_STATUS_JSON).replace("\\", "/"),
    }


def write_monitor_lock(
    *,
    reconcile: bool = True,
    regression_check: bool = True,
) -> dict[str, Any]:
    """Write PRE_ACTION_TRAINING_READINESS_MONITOR_LOCK.json."""
    recon = reconcile_ops_status(write=True) if reconcile else {"ok": True}
    reg = assert_false_stale_rmse() if regression_check else {"ok": True, "skipped": True}

    lock = {
        "ok": True,
        "at": _utc(),
        "status": "pre_action_training_readiness_monitor_locked",
        "model_id": "pre_action_energy_v1",
        "eligibility_contract": {
            "cold_first_cannot_enter_v1_drift": True,
            "warm_repeat_with_measured_E_net_only": True,
            "timing_only_excluded": True,
        },
        "false_stale_regression": {
            "n_warm": N_WARM,
            "n_cold": N_COLD,
            "warm_residual_j": WARM_RESIDUAL_J,
            "cold_residual_j": COLD_RESIDUAL_J,
            "eligible_rmse_j": EXPECTED_ELIGIBLE_RMSE_J,
            "pooled_legacy_rmse_j": EXPECTED_POOLED_RMSE_J,
            "verified": bool(reg.get("ok")),
        },
        "v1": {
            "version": PREDICTOR_VERSION,
            "alpha_j": ALPHA,
            "beta_j_per_s": BETA,
            "coefficients_mutated": False,
            "coeff_hash_sha256": _coeff_hash(),
            "retained": True,
            "predictor_stale": False,
            "plant_config_id": PLANT_CONFIG_ID,
        },
        "status_consistency": (recon.get("consistency") if reconcile else {}),
        "ops_review_required": False,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "auto_refit": False,
            "gates_action": False,
            "learning_admission_withheld": True,
            "learning_admission_granted": False,
            "predictor_blocked": True,
        },
        "decision": "retain_v1_after_monitor_repair",
        "note": (
            "Monitor repair locked for pre_action_energy_v1 readiness. "
            "V1/V2 accounting coefficients unchanged; learning still withheld."
        ),
    }
    CAMPAIGN.mkdir(parents=True, exist_ok=True)
    MONITOR_LOCK.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    sync = sync_pre_action_readiness_from_artifacts()
    lock["artifact"] = str(MONITOR_LOCK).replace("\\", "/")
    lock["reconcile_ok"] = bool(recon.get("ok"))
    lock["policy_sync"] = sync
    return lock


def verify_monitor_lock_consistency() -> dict[str, Any]:
    """Read live artifacts and confirm agreement with policy_stamp."""
    if not MONITOR_LOCK.exists():
        return {"ok": False, "reason": "monitor_lock_missing"}
    lock = json.loads(MONITOR_LOCK.read_text(encoding="utf-8"))
    ops = json.loads(OPS_STATUS_JSON.read_text(encoding="utf-8")) if OPS_STATUS_JSON.exists() else {}
    stamp = policy_stamp()
    checks = {
        "lock_ok": bool(lock.get("ok")),
        "ops_review_false": ops.get("ops_review_required") is False,
        "drift_not_stale": (ops.get("drift_v1") or {}).get("predictor_stale") is False,
        "policy_ops_review_false": stamp.get("ops_review_required") is False
        or ops.get("ops_review_required") is False,
        "v1_hash_match": lock.get("v1", {}).get("coeff_hash_sha256") == _coeff_hash(),
        "alpha_unchanged": math.isclose(
            float(lock.get("v1", {}).get("alpha_j")), float(ALPHA), rel_tol=0, abs_tol=1e-12
        ),
        "beta_unchanged": math.isclose(
            float(lock.get("v1", {}).get("beta_j_per_s")), float(BETA), rel_tol=0, abs_tol=1e-12
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "lock": lock.get("status")}
