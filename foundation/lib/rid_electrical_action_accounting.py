#!/usr/bin/env python3
"""Read-only GPU action accounting: estimate → measure → residual.

Never permits, denies, reroutes, or alters actions based on estimates.
"""
from __future__ import annotations

from typing import Any

from lib.rid_electrical_drift_check import (
    evaluate_live_accounting,
    load_drift_log,
    make_revalidation_fingerprint,
    record_accounting_use,
    refresh_and_apply_drift_status,
)
from lib.rid_electrical_policy import PREDICTOR_STALE, policy_stamp
from lib.rid_electrical_predictor import (
    HELD_OUT_RMSE_J,
    PLANT_CONFIG_ID,
    PREDICTOR_VERSION,
    predict_E_net,
    predict_with_error_scale,
)


def _predictor_state_label(*, confidence: str | None, drift_status: str | None) -> str:
    if confidence in {"out_of_validated_domain", "invalid_input", "config_mismatch"}:
        return str(confidence)
    if drift_status == "predictor_stale_revalidation_required" or PREDICTOR_STALE:
        return "stale"
    if drift_status == "live_accounting_validated":
        return "live_accounting_validated"
    if drift_status == "insufficient_live_sample":
        return "insufficient_live_sample"
    return confidence or "unknown"


def format_accounting_report(report: dict[str, Any]) -> str:
    pred = report.get("predicted_E_net_j")
    measured = report.get("measured_E_net_j")
    resid = report.get("residual_j")
    scale = report.get("heldout_rmse_j")
    state = report.get("predictor_state")
    pred_s = f"{pred:.1f}" if isinstance(pred, (int, float)) else "null"
    meas_s = f"{measured:.1f}" if isinstance(measured, (int, float)) else "null"
    resid_s = f"{resid:.1f}" if isinstance(resid, (int, float)) else "null"
    scale_s = f"{scale:.1f}" if isinstance(scale, (int, float)) else "?"
    return (
        "GPU inference accounting\n"
        f"Estimated: {pred_s} J ± {scale_s} J error scale\n"
        f"Measured: {meas_s} J\n"
        f"Residual: {resid_s} J\n"
        f"Predictor state: {state}"
    )


def account_gpu_inference(
    *,
    action_id: str,
    model: str,
    eval_duration_s: float | None,
    measured_E_net_j: float | None,
    actual_eval_tokens: int | float | None = None,
    session_id: str | None = None,
    plant_config_id: str | None = None,
    gpu_temp_start_c: float | None = None,
    gpu_temp_end_c: float | None = None,
    residency_state: str = "warm_repeat",
    action_type: str = "gpu_inference",
    planned_eval_duration_s: float | None = None,
    refresh_drift: bool = True,
    append_drift_log: bool = True,
    # V2 shadow (read-only; never gates; V1 remains approved fallback)
    prompt_eval_duration_s: float | None = None,
    measured_E_tail_j: float | None = None,
    tail_horizon_s: float | None = None,
    unload_before: bool = False,
    shadow_v2: bool = True,
) -> dict[str, Any]:
    """Post-action accounting for one GPU inference.

    Returns a report dict. Never gates the action.
    """
    cfg = plant_config_id or PLANT_CONFIG_ID
    pre = None
    if planned_eval_duration_s is not None:
        pre = predict_with_error_scale(float(planned_eval_duration_s))

    # If stale, still measure but withhold estimate (confidence reflects stale via drift)
    pred_result: dict[str, Any]
    if eval_duration_s is None:
        pred_result = {
            "predicted_E_net_j": None,
            "heldout_rmse_j": HELD_OUT_RMSE_J,
            "confidence": "invalid_input",
            "in_domain": False,
            "plant_configuration_id": PLANT_CONFIG_ID,
        }
    else:
        pred_result = predict_E_net(float(eval_duration_s), plant_config_id=cfg)

    # Refresh drift and apply stale gate: refuse new estimates when stale
    drift_status = None
    if refresh_drift:
        drift_eval = refresh_and_apply_drift_status()
        drift_status = drift_eval.get("status")
        if drift_eval.get("estimates_refused") or drift_eval.get("predictor_stale"):
            # Withhold estimate until revalidation; measurement still recorded.
            pred_result = {
                **pred_result,
                "predicted_E_net_j": None,
                "confidence": "predictor_stale_revalidation_required",
            }

    predicted = pred_result.get("predicted_E_net_j")
    residual = None
    if predicted is not None and measured_E_net_j is not None:
        residual = float(measured_E_net_j) - float(predicted)

    drift_rec = None
    if (
        append_drift_log
        and eval_duration_s is not None
        and measured_E_net_j is not None
        and str(residency_state) == "warm_repeat"
        and pred_result.get("in_domain")
        and pred_result.get("confidence") not in {
            "predictor_stale_revalidation_required",
            "config_mismatch",
            "invalid_input",
        }
    ):
        drift_rec = record_accounting_use(
            float(eval_duration_s),
            float(measured_E_net_j),
            session_id=str(session_id or action_id),
            plant_config_id=cfg,
            gpu_temp_settle_c=gpu_temp_start_c,
            residency=residency_state,
            revalidation_fingerprint=make_revalidation_fingerprint(
                plant_config_id=cfg,
                residency=residency_state,
            ),
            append=True,
        )
        # Re-evaluate after append
        if refresh_drift:
            drift_eval = refresh_and_apply_drift_status()
            drift_status = drift_eval.get("status")

    state = _predictor_state_label(
        confidence=pred_result.get("confidence"),
        drift_status=drift_status,
    )

    v2_shadow = None
    if shadow_v2 and tail_horizon_s is not None:
        try:
            from lib.rid_electrical_v2_shadow import shadow_account_v2

            v2_shadow = shadow_account_v2(
                action_id=action_id,
                session_id=session_id,
                t_eval_s=eval_duration_s,
                t_prompt_s=prompt_eval_duration_s,
                tail_horizon_s=float(tail_horizon_s),
                residency=residency_state,
                unload_before=unload_before,
                measured_E_net_j=measured_E_net_j,
                measured_E_tail_j=measured_E_tail_j,
                plant_config_id=cfg,
                append=True,
            )
        except Exception as exc:  # noqa: BLE001
            v2_shadow = {"ok": False, "shadowed": False, "error": str(exc)}

    registry = None
    try:
        from lib.rid_electrical_policy import ACCOUNTING_PREDICTOR_V2_APPROVED
        from lib.rid_electrical_predictor_registry import estimate_action
        from lib.rid_electrical_action_receipt import format_action_receipt

        request_tail = tail_horizon_s is not None
        # Prompt decomposition when prompt timing present and not pure V1 specialty
        request_prompt = bool(prompt_eval_duration_s) and (
            residency_state == "cold_first" or unload_before or request_tail
        )
        registry = estimate_action(
            t_eval_s=eval_duration_s,
            t_prompt_s=prompt_eval_duration_s,
            tail_horizon_s=tail_horizon_s if request_tail else None,
            residency=residency_state,
            unload_before=unload_before,
            request_tail_accounting=request_tail,
            request_prompt_decomposition=request_prompt,
            plant_config_id=cfg,
            measured_E_net_j=measured_E_net_j,
            measured_E_tail_j=measured_E_tail_j,
        )
        # After approval, enrich receipt fields from registry/V2 components
        if ACCOUNTING_PREDICTOR_V2_APPROVED and registry.get("component_estimates"):
            pass
    except Exception as exc:  # noqa: BLE001
        registry = {"ok": False, "error": str(exc)}

    from lib.rid_electrical_policy import ACCOUNTING_PREDICTOR_V2_APPROVED as _V2_APPR

    reg = registry if isinstance(registry, dict) else {}
    selected = reg.get("registry_selected_predictor")
    pred_reg = reg.get("predicted_E_j")
    meas_reg = reg.get("measured_E_j")
    if meas_reg is None:
        meas_reg = reg.get("measured_energy")
    if meas_reg is None:
        meas_reg = measured_E_net_j
    resid_reg = reg.get("residual_j")
    if resid_reg is None and pred_reg is not None and meas_reg is not None:
        resid_reg = float(meas_reg) - float(pred_reg)
    # Prefer registry residual when registry selected; keep V1 residual as fallback
    if selected in {"V1", "V2"} and resid_reg is not None:
        residual_out = resid_reg
    else:
        residual_out = residual if selected is None else resid_reg

    report = {
        "action_id": action_id,
        "action_type": action_type,
        "model": model,
        "plant_config_id": cfg,
        "predictor_version": PREDICTOR_VERSION,
        "planned_estimate": pre,
        "predicted_E_net_j": predicted,
        "measured_E_net_j": measured_E_net_j,
        "measured_E_tail_j": measured_E_tail_j,
        "residual_j": residual_out if residual_out is not None else residual,
        "eval_duration_s": eval_duration_s,
        "actual_eval_tokens": actual_eval_tokens,
        "thermal_start_c": gpu_temp_start_c,
        "thermal_end_c": gpu_temp_end_c,
        "residency_state": residency_state,
        "confidence": reg.get("confidence") or pred_result.get("confidence"),
        "heldout_rmse_j": pred_result.get("heldout_rmse_j", HELD_OUT_RMSE_J),
        "drift_status": drift_status,
        "predictor_state": state,
        "drift_record": drift_rec,
        "v2_shadow": v2_shadow,
        "registry": registry,
        "selected_predictor": selected,
        "registry_selected_predictor": selected,
        "selection_reason": reg.get("selection_reason"),
        "request_component": reg.get("request_component"),
        "component_estimates": reg.get("component_estimates"),
        "predicted_E_j": pred_reg,
        "measured_E_j": meas_reg,
        "measured_energy": meas_reg,
        "prediction_domain": reg.get("prediction_domain"),
        "drift_state_v1": reg.get("drift_state_v1"),
        "drift_state_v2": reg.get("drift_state_v2"),
        "registry_release_id": reg.get("registry_release_id"),
        "accounting_predictor_v2_approved": bool(_V2_APPR),
        "operational_authority": False,
        "master_routing_authorized": False,
        "auto_admit": False,
        "gates_action": False,
        "policy": policy_stamp(),
    }
    # Human report: receipt when registry active with components; else classic V1 line
    try:
        from lib.rid_electrical_action_receipt import format_action_receipt

        if report.get("component_estimates") or report.get("registry_selected_predictor"):
            report["human_report"] = format_action_receipt(report)
        else:
            report["human_report"] = format_accounting_report(report)
    except Exception:  # noqa: BLE001
        report["human_report"] = format_accounting_report(report)
    return report
