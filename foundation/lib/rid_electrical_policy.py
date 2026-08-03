#!/usr/bin/env python3
"""Electrical lane policy after decisive negative Δ_info (closed prediction branch).

Lifecycle (authoritative):
  rejected_operational_use

Rail telemetry role:
  observe_only_diagnostics

Electrical must not enter A(t), Master S_n, prediction features, or routing
decisions under current evidence. Authority scaffolds remain in-tree as
evidence of what was examined; all write/apply paths fail closed.

Reopen Master/prediction electrical work only when a material change is
defined *before* collecting new data (see REOPEN_CONDITIONS).
"""
from __future__ import annotations

from typing import Any, Sequence

# --- Locked post-decisive states ---
LIFECYCLE = "rejected_operational_use"
RAIL_ROLE = "observe_only_diagnostics"
PREDICTION_BRANCH = "closed_negative_result"

# Authority paths permanently disabled (code retained; flags cannot override).
MASTER_WEIGHT_ENABLED = False
ADVISORY_ROUTING_ENABLED = False
CANARY_ENABLED = False
PREDICTOR_OPERATIONAL = False
ELECTRICAL_IN_A_T = False
ADMISSION_GRANTED = False

AUTHORITATIVE_ARTIFACTS = (
    "decisive_evidence_latest.json",
    "decisive_evidence_latest.md",
    "role_decision_latest.json",
    "role_decision_latest.md",
    "corpus_freeze_manifest.json",
    "prediction_postmortem_latest.json",
    "CLOSED_PREDICTION_BRANCH.json",
)

REOPEN_CONDITIONS: tuple[str, ...] = (
    "independent_hardware_current_meters",
    "substantially_different_sensors",
    "new_cpu_power_instrumentation",
    "different_hardware",
    "different_prediction_target",
    "new_physical_hypothesis_defined_before_data_collection",
)

# Not sufficient to reopen:
REOPEN_NOT_SUFFICIENT: tuple[str, ...] = (
    "more_sessions_same_measurement_construction",
    "searching_for_favorable_window",
    "smoke_or_short_reruns",
)

DIAGNOSTIC_ALLOWED: tuple[str, ...] = (
    "board_power_distribution",
    "voltage_anomalies",
    "derived_current_ohm_stamped",
    "missing_or_stale_sensors",
    "unusual_pcie_vs_8pin_behavior",
    "forensic_state_during_crash_or_throttle",
)

NEXT_EXPERIMENT_HINT = (
    "Controlled ledger campaign (rid_electrical_ledger_campaign_v1): "
    "one-factor cells + CV_E/CV_P gates. Learning admission withheld until "
    "repeatable signatures; predictor blocked. Not Master/routing."
)

OUTCOMES_EXPERIMENT_ID = "rid_electrical_outcomes_v1"
LEDGER_EXPERIMENT_ID = "rid_electrical_action_ledger_v1"
LEDGER_CAMPAIGN_ID = "rid_electrical_ledger_campaign_v1"
OUTCOMES_ENTERS_MASTER = False
OUTCOMES_ENTERS_A_T = False
OUTCOMES_OPERATIONAL = False

# Energy-outcome learning (Ê predictor) — separate from Master; still withheld
LEARNING_ADMISSION_WITHHELD = True
LEARNING_ADMISSION_GRANTED = False
# PREDICTOR_BLOCKED = blocked from operational control (Master/routing/action
# selection), NOT blocked from guarded accounting estimate calls.
PREDICTOR_BLOCKED = True
NARROW_ACCOUNTING_PREDICTOR_CANDIDATE = True  # eval_duration_v1, separate review only
ACCOUNTING_PREDICTOR_APPROVED = True  # separate review passed; accounting-only use authorized
ACCOUNTING_ESTIMATES_AUTHORIZED = True
LIVE_ACCOUNTING_VALIDATED = False  # set True only after live_accounting_validation verdict
PREDICTOR_STALE = False  # set True only when live RMSE exceeds 1.5x held-out RMSE
PREDICTOR_V1_FROZEN = True  # immutable baseline; coefficient changes require eval_duration_v2
V2_PREDICTOR_CANDIDATE = False  # set True only after prospective validation pass
ACCOUNTING_PREDICTOR_V2_APPROVED = False  # component-wise; set by approval review only
PREDICTOR_V2_STALE = False
V2_APPROVED_COMPONENTS: tuple[str, ...] = ()
V2_LIVE_SHADOW_VALIDATED = False
PRODUCTION_ACCOUNTING_REGISTRY_VALIDATED = False
PRODUCTION_ACCOUNTING_OPERATIONS = False  # set True only after ops bootstrap artifact
OPS_REVIEW_REQUIRED = False
OPS_REVIEW_REASON: str | None = None
ENERGY_LEARNING_STATE = {
    "accounting_implemented": True,
    "measurements_valid": True,
    "cost_signatures_repeatable": True,
    "learning_admission_withheld": True,
    "predictor_candidate_status": "eval_duration_v1_for_separate_review",
    "predictor_operational": False,
    "narrow_accounting_estimate_only": True,
    "accounting_predictor_approved": True,
    "accounting_estimates_authorized": True,
    "live_accounting_validated": False,
    "predictor_stale": False,
    "predictor_v1_frozen": True,
    "refit_forbidden": True,
    "next_model_id": "action_energy_v2_candidate",
    "v2_predictor_candidate": False,
    "accounting_predictor_v2_approved": False,
    "predictor_v2_stale": False,
    "v2_live_shadow_validated": False,
    "v2_approved_components": [],
    "production_accounting_registry_validated": False,
    "production_accounting_operations": False,
    "ops_review_required": False,
    "ops_review_reason": None,
    "predictor_blocked_meaning": "blocked_from_operational_control_not_guarded_accounting",
    # pre_action_energy_v1 readiness (shadow-only; defaults withheld)
    "pre_action_training_readiness": False,
    "pre_action_corpus_ready": False,
    "pre_action_offline_candidate": False,
    "pre_action_shadow_validated": False,
    "pre_action_model_id": "pre_action_energy_v1",
}



PROVEN_PLANT_FOCUS: tuple[str, ...] = (
    "thermal_gradients",
    "coolant_behavior",
    "load",
    "vram_headroom",
    "transition_rates",
    "existing_rid_subsystem_states",
)


class ElectricalAuthorityDenied(RuntimeError):
    """Fail-closed: prediction/Master/routing electrical authority is closed."""


def sync_live_accounting_from_artifact() -> dict[str, Any]:
    """Load latest live accounting verdict artifact into module lifecycle flags."""
    global LIVE_ACCOUNTING_VALIDATED, PREDICTOR_STALE
    try:
        from lib.paths import AUTO_ARTIFACTS

        path = (
            AUTO_ARTIFACTS
            / "rid_electrical"
            / "ledger_campaign"
            / "live_accounting_validation_latest.json"
        )
        if not path.exists():
            return {
                "synced": False,
                "live_accounting_validated": LIVE_ACCOUNTING_VALIDATED,
                "predictor_stale": PREDICTOR_STALE,
            }
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        status = ((data.get("evaluation") or {}).get("status")) or data.get("status")
        return apply_live_accounting_verdict(str(status or ""))
    except Exception:  # noqa: BLE001
        return {
            "synced": False,
            "live_accounting_validated": LIVE_ACCOUNTING_VALIDATED,
            "predictor_stale": PREDICTOR_STALE,
        }


def sync_v2_candidate_from_artifact() -> dict[str, Any]:
    """Sync V2 candidate flag from prospective validation artifact."""
    try:
        from lib.paths import AUTO_ARTIFACTS
        import json

        path = (
            AUTO_ARTIFACTS
            / "rid_electrical"
            / "ledger_campaign"
            / "v2_prospective_validation_latest.json"
        )
        if not path.exists():
            return {"synced": False, "v2_predictor_candidate": V2_PREDICTOR_CANDIDATE}
        data = json.loads(path.read_text(encoding="utf-8"))
        passed = bool(data.get("prospective_pass")) or data.get("status") == "v2_predictor_candidate"
        return apply_v2_candidate_verdict(passed)
    except Exception:  # noqa: BLE001
        return {"synced": False, "v2_predictor_candidate": V2_PREDICTOR_CANDIDATE}


def sync_v2_approval_from_artifact() -> dict[str, Any]:
    """Sync V2 accounting approval + live-shadow flags from approval artifacts."""
    try:
        from lib.paths import AUTO_ARTIFACTS
        import json

        apath = (
            AUTO_ARTIFACTS
            / "rid_electrical"
            / "ledger_campaign"
            / "PREDICTOR_V2_APPROVED.json"
        )
        vpath = (
            AUTO_ARTIFACTS
            / "rid_electrical"
            / "ledger_campaign"
            / "v2_live_shadow_validation_latest.json"
        )
        if vpath.exists():
            vdata = json.loads(vpath.read_text(encoding="utf-8"))
            live = str(vdata.get("live_status") or "")
            if live in {"v2_live_shadow_validated", "v2_live_shadow_failed"}:
                apply_v2_live_verdict(live)
        if not apath.exists():
            return {
                "synced": False,
                "accounting_predictor_v2_approved": ACCOUNTING_PREDICTOR_V2_APPROVED,
            }
        data = json.loads(apath.read_text(encoding="utf-8"))
        comps = list(data.get("approved_components") or [])
        full = bool(data.get("full_approval") or data.get("accounting_predictor_v2_approved"))
        return apply_v2_approval_verdict(approved_components=comps, full_approval=full)
    except Exception:  # noqa: BLE001
        return {
            "synced": False,
            "accounting_predictor_v2_approved": ACCOUNTING_PREDICTOR_V2_APPROVED,
        }


def sync_accounting_ops_from_artifact() -> dict[str, Any]:
    """Sync production accounting ops + registry-validated flags from artifacts."""
    global PRODUCTION_ACCOUNTING_REGISTRY_VALIDATED
    try:
        from lib.paths import AUTO_ARTIFACTS
        import json

        hpath = (
            AUTO_ARTIFACTS
            / "rid_electrical"
            / "ledger_campaign"
            / "registry_health_latest.json"
        )
        if hpath.exists():
            hdata = json.loads(hpath.read_text(encoding="utf-8"))
            PRODUCTION_ACCOUNTING_REGISTRY_VALIDATED = (
                str(hdata.get("status") or "")
                == "production_accounting_registry_validated"
            )
            ENERGY_LEARNING_STATE["production_accounting_registry_validated"] = (
                PRODUCTION_ACCOUNTING_REGISTRY_VALIDATED
            )
        opath = (
            AUTO_ARTIFACTS
            / "rid_electrical"
            / "ledger_campaign"
            / "PRODUCTION_ACCOUNTING_OPS_STATUS.json"
        )
        if not opath.exists():
            return {
                "synced": False,
                "production_accounting_operations": PRODUCTION_ACCOUNTING_OPERATIONS,
                "production_accounting_registry_validated": (
                    PRODUCTION_ACCOUNTING_REGISTRY_VALIDATED
                ),
            }
        data = json.loads(opath.read_text(encoding="utf-8"))
        return apply_accounting_ops_verdict(
            status=str(data.get("status") or ""),
            ops_review_required=bool(data.get("ops_review_required")),
            review_reason=data.get("review_reason"),
        )
    except Exception:  # noqa: BLE001
        return {
            "synced": False,
            "production_accounting_operations": PRODUCTION_ACCOUNTING_OPERATIONS,
        }


def policy_stamp() -> dict[str, Any]:
    sync_live_accounting_from_artifact()
    sync_v2_candidate_from_artifact()
    sync_v2_approval_from_artifact()
    sync_accounting_ops_from_artifact()
    return {
        "lifecycle": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "prediction_branch": PREDICTION_BRANCH,
        "master_weight_enabled": MASTER_WEIGHT_ENABLED,
        "advisory_routing_enabled": ADVISORY_ROUTING_ENABLED,
        "canary_enabled": CANARY_ENABLED,
        "predictor_operational": PREDICTOR_OPERATIONAL,
        "electrical_in_A_t": ELECTRICAL_IN_A_T,
        "admission_granted": ADMISSION_GRANTED,
        "outcomes_enters_master": OUTCOMES_ENTERS_MASTER,
        "learning_admission_withheld": LEARNING_ADMISSION_WITHHELD,
        "learning_admission_granted": LEARNING_ADMISSION_GRANTED,
        "predictor_blocked": PREDICTOR_BLOCKED,
        "narrow_accounting_predictor_candidate": NARROW_ACCOUNTING_PREDICTOR_CANDIDATE,
        "accounting_predictor_approved": ACCOUNTING_PREDICTOR_APPROVED,
        "accounting_estimates_authorized": ACCOUNTING_ESTIMATES_AUTHORIZED,
        "live_accounting_validated": LIVE_ACCOUNTING_VALIDATED,
        "predictor_stale": PREDICTOR_STALE,
        "predictor_v1_frozen": PREDICTOR_V1_FROZEN,
        "v2_predictor_candidate": V2_PREDICTOR_CANDIDATE,
        "accounting_predictor_v2_approved": ACCOUNTING_PREDICTOR_V2_APPROVED,
        "predictor_v2_stale": PREDICTOR_V2_STALE,
        "v2_live_shadow_validated": V2_LIVE_SHADOW_VALIDATED,
        "v2_approved_components": list(V2_APPROVED_COMPONENTS),
        "production_accounting_registry_validated": (
            PRODUCTION_ACCOUNTING_REGISTRY_VALIDATED
        ),
        "production_accounting_operations": PRODUCTION_ACCOUNTING_OPERATIONS,
        "ops_review_required": OPS_REVIEW_REQUIRED,
        "ops_review_reason": OPS_REVIEW_REASON,
        "predictor_blocked_meaning": (
            "blocked_from_operational_control_not_guarded_accounting"
        ),
        "energy_learning_state": dict(ENERGY_LEARNING_STATE),
        "diagnostic_allowed": list(DIAGNOSTIC_ALLOWED),
        "reopen_conditions": list(REOPEN_CONDITIONS),
        "reopen_not_sufficient": list(REOPEN_NOT_SUFFICIENT),
        "proven_plant_focus": list(PROVEN_PLANT_FOCUS),
        "next_experiment_hint": NEXT_EXPERIMENT_HINT,
        "authoritative_artifacts": list(AUTHORITATIVE_ARTIFACTS),
    }


def apply_live_accounting_verdict(verdict: str) -> dict[str, Any]:
    """Update live-validation lifecycle flags from a live accounting verdict.

    Never grants operational/Master/routing authority.
    """
    global LIVE_ACCOUNTING_VALIDATED, PREDICTOR_STALE
    if verdict == "live_accounting_validated":
        LIVE_ACCOUNTING_VALIDATED = True
        PREDICTOR_STALE = False
    elif verdict == "predictor_stale_revalidation_required":
        LIVE_ACCOUNTING_VALIDATED = False
        PREDICTOR_STALE = True
    elif verdict == "insufficient_live_sample":
        # Keep prior validated/stale unless explicitly cleared by caller.
        pass
    else:
        LIVE_ACCOUNTING_VALIDATED = False
    ENERGY_LEARNING_STATE["live_accounting_validated"] = LIVE_ACCOUNTING_VALIDATED
    ENERGY_LEARNING_STATE["predictor_stale"] = PREDICTOR_STALE
    return {
        "verdict": verdict,
        "live_accounting_validated": LIVE_ACCOUNTING_VALIDATED,
        "predictor_stale": PREDICTOR_STALE,
        "operational_authority": False,
        "master_routing_authorized": False,
        "auto_admit": False,
    }


def apply_v2_candidate_verdict(passed: bool) -> dict[str, Any]:
    """Mark V2 as predictor candidate after prospective validation.

    Never grants accounting_predictor_v2_approved or operational authority.
    """
    global V2_PREDICTOR_CANDIDATE
    V2_PREDICTOR_CANDIDATE = bool(passed)
    ENERGY_LEARNING_STATE["v2_predictor_candidate"] = V2_PREDICTOR_CANDIDATE
    ENERGY_LEARNING_STATE["accounting_predictor_v2_approved"] = False
    ENERGY_LEARNING_STATE["next_model_id"] = (
        "action_energy_v2_candidate" if passed else "retain_v1_decomposition_diagnostic_only"
    )
    ENERGY_LEARNING_STATE["predictor_candidate_status"] = (
        "v2_predictor_candidate" if passed else "v2_prospective_failed"
    )
    return {
        "v2_predictor_candidate": V2_PREDICTOR_CANDIDATE,
        "accounting_predictor_v2_approved": False,
        "predictor_v1_frozen": PREDICTOR_V1_FROZEN,
        "operational_authority": False,
        "master_routing_authorized": False,
        "auto_admit": False,
    }


def apply_v2_live_verdict(verdict: str) -> dict[str, Any]:
    """Apply V2 live-shadow / drift verdict. Never auto-refits."""
    global PREDICTOR_V2_STALE, V2_LIVE_SHADOW_VALIDATED
    if verdict == "v2_live_shadow_validated":
        V2_LIVE_SHADOW_VALIDATED = True
        PREDICTOR_V2_STALE = False
    elif verdict == "v2_stale_revalidation_required":
        PREDICTOR_V2_STALE = True
    elif verdict == "v2_live_shadow_failed":
        V2_LIVE_SHADOW_VALIDATED = False
    ENERGY_LEARNING_STATE["v2_live_shadow_validated"] = V2_LIVE_SHADOW_VALIDATED
    ENERGY_LEARNING_STATE["predictor_v2_stale"] = PREDICTOR_V2_STALE
    return {
        "verdict": verdict,
        "v2_live_shadow_validated": V2_LIVE_SHADOW_VALIDATED,
        "predictor_v2_stale": PREDICTOR_V2_STALE,
        "operational_authority": False,
        "master_routing_authorized": False,
        "auto_admit": False,
    }


def apply_v2_approval_verdict(
    *,
    approved_components: Sequence[str],
    full_approval: bool,
) -> dict[str, Any]:
    """Grant component-wise V2 accounting approval. Never opens Master/routing."""
    global ACCOUNTING_PREDICTOR_V2_APPROVED, V2_APPROVED_COMPONENTS
    comps = tuple(sorted({str(c) for c in approved_components}))
    V2_APPROVED_COMPONENTS = comps
    ACCOUNTING_PREDICTOR_V2_APPROVED = bool(full_approval) and len(comps) > 0
    ENERGY_LEARNING_STATE["accounting_predictor_v2_approved"] = ACCOUNTING_PREDICTOR_V2_APPROVED
    ENERGY_LEARNING_STATE["v2_approved_components"] = list(comps)
    ENERGY_LEARNING_STATE["next_model_id"] = (
        "accounting_predictor_v2_approved"
        if ACCOUNTING_PREDICTOR_V2_APPROVED
        else "v2_partial_component_approval"
    )
    ENERGY_LEARNING_STATE["predictor_candidate_status"] = (
        "accounting_predictor_v2_approved"
        if ACCOUNTING_PREDICTOR_V2_APPROVED
        else "v2_partial_component_approval"
    )
    return {
        "accounting_predictor_v2_approved": ACCOUNTING_PREDICTOR_V2_APPROVED,
        "v2_approved_components": list(comps),
        "predictor_v1_frozen": PREDICTOR_V1_FROZEN,
        "operational_authority": False,
        "master_routing_authorized": False,
        "auto_admit": False,
    }


def apply_accounting_ops_verdict(
    *,
    status: str,
    ops_review_required: bool = False,
    review_reason: str | None = None,
) -> dict[str, Any]:
    """Apply production accounting ops status. Never grants Master/routing/auto-admit."""
    global PRODUCTION_ACCOUNTING_OPERATIONS, OPS_REVIEW_REQUIRED, OPS_REVIEW_REASON
    PRODUCTION_ACCOUNTING_OPERATIONS = status == "production_accounting_operations"
    OPS_REVIEW_REQUIRED = bool(ops_review_required)
    OPS_REVIEW_REASON = str(review_reason) if review_reason else None
    ENERGY_LEARNING_STATE["production_accounting_operations"] = (
        PRODUCTION_ACCOUNTING_OPERATIONS
    )
    ENERGY_LEARNING_STATE["ops_review_required"] = OPS_REVIEW_REQUIRED
    ENERGY_LEARNING_STATE["ops_review_reason"] = OPS_REVIEW_REASON
    if PRODUCTION_ACCOUNTING_OPERATIONS:
        ENERGY_LEARNING_STATE["next_model_id"] = "production_accounting_operations"
        ENERGY_LEARNING_STATE["predictor_candidate_status"] = (
            "production_accounting_operations"
        )
    return {
        "status": status,
        "production_accounting_operations": PRODUCTION_ACCOUNTING_OPERATIONS,
        "ops_review_required": OPS_REVIEW_REQUIRED,
        "ops_review_reason": OPS_REVIEW_REASON,
        "operational_authority": False,
        "master_routing_authorized": False,
        "auto_admit": False,
    }


def assert_master_write_forbidden(*, context: str = "") -> None:
    """Any accidental Master electrical write path must fail closed."""
    raise ElectricalAuthorityDenied(
        f"electrical_master_write_forbidden:{LIFECYCLE}:{context}"
    )


def assert_routing_behavior_forbidden(*, context: str = "") -> None:
    raise ElectricalAuthorityDenied(
        f"electrical_routing_behavior_forbidden:{LIFECYCLE}:{context}"
    )


def assert_predictor_operational_forbidden(*, context: str = "") -> None:
    raise ElectricalAuthorityDenied(
        f"electrical_predictor_non_operational:{LIFECYCLE}:{context}"
    )


def gate_canary_apply(*, apply: bool, context: str = "canary") -> dict[str, Any]:
    """Canary apply always blocked after negative decisive evidence."""
    if apply:
        return {
            "allowed": False,
            "applied": False,
            "reason": f"permanently_disabled_{LIFECYCLE}",
            "context": context,
        }
    return {
        "allowed": False,
        "applied": False,
        "reason": "canary_disabled_dry_run_only",
        "context": context,
    }


def gate_advisory_behavior(*, request_behavior_change: bool = False) -> dict[str, Any]:
    if request_behavior_change:
        assert_routing_behavior_forbidden(context="advisory")
    return {
        "advisory_routing_enabled": False,
        "authority": "observe_only_diagnostics_no_behavior",
        "predictor_operational": False,
    }
