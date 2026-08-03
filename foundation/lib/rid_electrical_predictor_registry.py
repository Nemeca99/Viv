#!/usr/bin/env python3
"""V1/V2 domain registry for guarded electrical accounting.

Predictor(x) =
  V1   if warm-resident eval-only and 2.5 ≤ t_eval ≤ 4.5
       and no cold load and no expanded tail / prompt decomposition
  V2   if cold load, prompt-decomposition, or defined tail accounting
       AND mapped component ∈ V2_APPROVED_COMPONENTS
  null outside either validated domain, V2 stale on expanded domain,
       or rejected stratum (tail_5 / warm_prompt_eval — no nearby fallback)

Never gates actions. Master/routing/auto-admit remain false.
"""
from __future__ import annotations

from typing import Any

from lib.rid_electrical_predictor import (
    DOMAIN_MAX_S,
    DOMAIN_MIN_S,
    predict_E_net as predict_v1,
)
from lib.rid_electrical_predictor_v2 import (
    T_EVAL_MAX_S,
    T_EVAL_MIN_S,
    predict_E_action,
    residency_is_cold,
)
from lib.rid_electrical_policy import (
    ACCOUNTING_PREDICTOR_V2_APPROVED,
    PREDICTOR_V1_FROZEN,
    V2_APPROVED_COMPONENTS,
)
import lib.rid_electrical_policy as _policy

REJECTED_STRATA = frozenset({"tail_5", "warm_prompt_eval"})


def map_request_component(
    *,
    residency: str = "warm_repeat",
    unload_before: bool = False,
    request_tail_accounting: bool = False,
    request_prompt_decomposition: bool = False,
    tail_horizon_s: float | None = None,
) -> str | None:
    """Map an accounting request to a V2 approval component id.

    Priority:
      - cold → load (covers cold with any measured tail; load is approved)
      - explicit tail accounting on warm → tail_{5|10|20} (no nearby remap)
      - warm prompt decomposition → warm_prompt_eval
    """
    cold = residency_is_cold(residency, unload_before=unload_before)
    if cold:
        if request_prompt_decomposition and not request_tail_accounting:
            return "prompt_eval"
        return "load"

    if request_tail_accounting and tail_horizon_s is not None:
        th = float(tail_horizon_s)
        if abs(th - 5.0) <= 0.5:
            return "tail_5"
        if abs(th - 10.0) <= 0.5:
            return "tail_10"
        if abs(th - 20.0) <= 0.5:
            return "tail_20"
        return "tail_unvalidated"

    if request_prompt_decomposition:
        return "warm_prompt_eval"

    return None


def _horizon_nearest_approved(th: float, approved: set[str]) -> float | None:
    """Intentionally unused for emission — nearby fallback is forbidden."""
    _ = (th, approved)
    return None


def select_predictor(
    *,
    t_eval_s: float | None,
    residency: str = "warm_repeat",
    unload_before: bool = False,
    request_tail_accounting: bool = False,
    request_prompt_decomposition: bool = False,
    tail_horizon_s: float | None = None,
) -> dict[str, Any]:
    """Choose V1, V2, or null for this accounting context."""
    cold = residency_is_cold(residency, unload_before=unload_before)
    component = map_request_component(
        residency=residency,
        unload_before=unload_before,
        request_tail_accounting=request_tail_accounting,
        request_prompt_decomposition=request_prompt_decomposition,
        tail_horizon_s=tail_horizon_s,
    )

    if t_eval_s is None:
        return {
            "selected": None,
            "selection_reason": "missing_t_eval",
            "domain": "invalid",
            "cold": cold,
            "request_component": component,
        }

    te = float(t_eval_s)
    expanded = bool(
        cold or request_tail_accounting or request_prompt_decomposition
    )

    # Expanded physical decomposition → V2 (if approved component / not stale)
    if expanded:
        if _policy.PREDICTOR_V2_STALE:
            return {
                "selected": None,
                "selection_reason": "v2_stale_expanded_domain_null",
                "domain": "expanded_stale",
                "cold": cold,
                "request_component": component,
            }
        if component in REJECTED_STRATA:
            return {
                "selected": None,
                "selection_reason": f"rejected_stratum:{component}",
                "domain": "rejected_stratum",
                "cold": cold,
                "request_component": component,
                "confidence": "rejected_stratum",
            }
        approved = set(_policy.V2_APPROVED_COMPONENTS) or set(V2_APPROVED_COMPONENTS)
        if ACCOUNTING_PREDICTOR_V2_APPROVED and component is not None:
            if component not in approved:
                return {
                    "selected": None,
                    "selection_reason": f"rejected_stratum:{component}",
                    "domain": "rejected_stratum",
                    "cold": cold,
                    "request_component": component,
                    "confidence": "rejected_stratum",
                }
        if not (T_EVAL_MIN_S <= te <= T_EVAL_MAX_S):
            return {
                "selected": None,
                "selection_reason": "v2_out_of_validated_domain",
                "domain": "ood",
                "cold": cold,
                "request_component": component,
            }
        domain = (
            "cold_load"
            if cold
            else (
                "prompt_decomp"
                if request_prompt_decomposition and not request_tail_accounting
                else "tail_accounting"
            )
        )
        return {
            "selected": "V2",
            "selection_reason": f"expanded_coverage:{domain}",
            "domain": domain,
            "cold": cold,
            "request_component": component,
        }

    # Narrow warm eval-only → V1
    if (
        not cold
        and DOMAIN_MIN_S <= te <= DOMAIN_MAX_S
        and not request_tail_accounting
        and not request_prompt_decomposition
    ):
        return {
            "selected": "V1",
            "selection_reason": "warm_eval_only_v1_specialty",
            "domain": "warm_eval_net",
            "cold": False,
            "request_component": None,
        }

    return {
        "selected": None,
        "selection_reason": "outside_v1_and_v2_validated_domains",
        "domain": "ood",
        "cold": cold,
        "request_component": component,
    }


def estimate_action(
    *,
    t_eval_s: float | None,
    t_prompt_s: float | None = None,
    tail_horizon_s: float | None = None,
    residency: str = "warm_repeat",
    unload_before: bool = False,
    request_tail_accounting: bool = False,
    request_prompt_decomposition: bool = False,
    plant_config_id: str | None = None,
    measured_E_net_j: float | None = None,
    measured_E_tail_j: float | None = None,
) -> dict[str, Any]:
    """Registry-selected estimate plus both-model shadow fields. Never gates."""
    release_id = None
    try:
        from lib.rid_electrical_accounting_registry_release import get_release_id

        release_id = get_release_id()
    except Exception:  # noqa: BLE001
        release_id = None

    sel = select_predictor(
        t_eval_s=t_eval_s,
        residency=residency,
        unload_before=unload_before,
        request_tail_accounting=request_tail_accounting,
        request_prompt_decomposition=request_prompt_decomposition,
        tail_horizon_s=tail_horizon_s,
    )
    component = sel.get("request_component")

    v1 = None
    if t_eval_s is not None:
        v1 = predict_v1(float(t_eval_s), plant_config_id=plant_config_id)

    v2 = None
    # Only compute V2 numeric path when not a rejected stratum (no nearby fallback)
    allow_v2_numeric = component not in REJECTED_STRATA and (
        component is None
        or component in set(_policy.V2_APPROVED_COMPONENTS)
        or not ACCOUNTING_PREDICTOR_V2_APPROVED
    )
    if (
        t_eval_s is not None
        and tail_horizon_s is not None
        and allow_v2_numeric
        and sel.get("selected") == "V2"
    ):
        v2 = predict_E_action(
            t_eval_s=float(t_eval_s),
            t_prompt_s=float(t_prompt_s or 0.0),
            tail_horizon_s=float(tail_horizon_s),
            residency=residency,
            unload_before=unload_before,
            plant_config_id=plant_config_id,
        )
    elif (
        t_eval_s is not None
        and tail_horizon_s is not None
        and component in REJECTED_STRATA
    ):
        # Shadow-only: still compute for diagnostics but never select
        v2 = predict_E_action(
            t_eval_s=float(t_eval_s),
            t_prompt_s=float(t_prompt_s or 0.0),
            tail_horizon_s=float(tail_horizon_s),
            residency=residency,
            unload_before=unload_before,
            plant_config_id=plant_config_id,
        )

    e_meas = None
    if measured_E_net_j is not None:
        e_meas = float(measured_E_net_j)
        if measured_E_tail_j is not None and request_tail_accounting:
            e_meas += float(measured_E_tail_j)

    v1_hat = (v1 or {}).get("predicted_E_net_j")
    v2_hat = (v2 or {}).get("predicted_E_action_j") if request_tail_accounting else (
        (v2 or {}).get("predicted_E_net_j")
    )

    selected = sel.get("selected")
    if selected == "V1" and _policy.PREDICTOR_STALE:
        selected = None
        sel = {
            **sel,
            "selected": None,
            "selection_reason": "v1_stale_revalidation_required",
            "domain": "warm_eval_net_stale",
            "confidence": "predictor_stale_revalidation_required",
        }
    if selected == "V2" and _policy.PREDICTOR_V2_STALE:
        selected = None
        sel = {**sel, "selected": None, "selection_reason": "v2_stale_override"}

    # Hard gate: rejected strata never emit selected V2 numeric
    if component in REJECTED_STRATA:
        selected = None
        sel = {
            **sel,
            "selected": None,
            "selection_reason": f"rejected_stratum:{component}",
            "domain": "rejected_stratum",
            "confidence": "rejected_stratum",
        }

    # Config mismatch → never emit numeric estimate
    if (v1 or {}).get("confidence") == "config_mismatch" and selected == "V1":
        selected = None
        sel = {
            **sel,
            "selected": None,
            "selection_reason": "config_mismatch",
            "domain": "config_mismatch",
        }
    if (v2 or {}).get("confidence") == "config_mismatch" and selected == "V2":
        selected = None
        sel = {
            **sel,
            "selected": None,
            "selection_reason": "config_mismatch",
            "domain": "config_mismatch",
        }

    pred = None
    scale = None
    components = None
    domain = sel.get("domain")
    confidence = sel.get("confidence") or "null_selection"
    if selected == "V1" and v1_hat is not None:
        pred = float(v1_hat)
        scale = (v1 or {}).get("empirical_error_scale_j")
        confidence = (v1 or {}).get("confidence") or "ok"
        domain = "warm_eval_net"
    elif selected == "V2" and v2 is not None and (v2 or {}).get("confidence") == "ok":
        pred = float(v2_hat) if v2_hat is not None else None
        scale = v2.get("empirical_error_scale_j")
        components = v2.get("component_estimates")
        confidence = v2.get("confidence")
        domain = v2.get("prediction_domain") or domain
    elif component in REJECTED_STRATA:
        confidence = "rejected_stratum"
        pred = None
        components = None

    residual_j = None
    if pred is not None and e_meas is not None:
        residual_j = float(e_meas) - float(pred)
    elif pred is not None and measured_E_net_j is not None and selected == "V1":
        residual_j = float(measured_E_net_j) - float(pred)

    v1_resid = None
    if v1_hat is not None and measured_E_net_j is not None:
        v1_resid = float(measured_E_net_j) - float(v1_hat)
    v2_resid = None
    if v2_hat is not None and e_meas is not None:
        v2_resid = float(e_meas) - float(v2_hat)

    drift_v1 = "stale" if _policy.PREDICTOR_STALE else "ok"
    drift_v2 = "stale" if _policy.PREDICTOR_V2_STALE else "ok"

    # Silence unused helper (documents forbidden nearby fallback)
    _ = _horizon_nearest_approved

    return {
        "registry_selected_predictor": selected,
        "selected_predictor": selected,
        "selection_reason": sel.get("selection_reason"),
        "request_component": component,
        "prediction_domain": domain,
        "predicted_E_j": pred,
        "measured_E_j": e_meas if e_meas is not None else measured_E_net_j,
        "residual_j": residual_j,
        "empirical_error_scale_j": scale,
        "component_estimates": components,
        "confidence": confidence,
        "drift_state_v1": drift_v1,
        "drift_state_v2": drift_v2,
        "registry_release_id": release_id,
        "plant_config_id": plant_config_id,
        "v1_prediction": v1_hat,
        "v2_prediction": v2_hat,
        "v1_result": v1,
        "v2_result": v2,
        "measured_energy": e_meas,
        "measured_E_net_j": measured_E_net_j,
        "measured_E_tail_j": measured_E_tail_j,
        "v1_residual": v1_resid,
        "v2_residual": v2_resid,
        "predictor_v1_frozen": bool(PREDICTOR_V1_FROZEN),
        "accounting_predictor_v2_approved": bool(_policy.ACCOUNTING_PREDICTOR_V2_APPROVED),
        "v2_approved_components": list(_policy.V2_APPROVED_COMPONENTS),
        "operational_authority": False,
        "master_routing_authorized": False,
        "auto_admit": False,
        "gates_action": False,
    }
