#!/usr/bin/env python3
"""Non-gating ordinary Viv GPU accounting hook (speak paths).

Never raises into the caller. Never gates speak/inference success.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ns_to_s(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    # Ollama reports nanoseconds; values < 1e6 treated as already seconds
    if x > 1e6:
        return x / 1e9
    return x


def timings_from_ollama_raw(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Extract eval/prompt timings and token counts from Ollama generate/chat raw."""
    data = raw or {}
    # chat completions may nest usage differently; prefer top-level ollama fields
    eval_s = _ns_to_s(data.get("eval_duration"))
    prompt_s = _ns_to_s(data.get("prompt_eval_duration"))
    eval_count = data.get("eval_count")
    if eval_count is None:
        usage = data.get("usage") or {}
        eval_count = usage.get("completion_tokens") or usage.get("total_tokens")
    return {
        "eval_duration_s": eval_s,
        "prompt_eval_duration_s": prompt_s,
        "actual_eval_tokens": eval_count,
    }


def record_ordinary_gpu_action(
    *,
    model: str | None = None,
    raw: dict[str, Any] | None = None,
    action_type: str = "viv_speak_generate",
    session_id: str | None = None,
    action_id: str | None = None,
    residency_state: str = "warm_repeat",
    measured_E_net_j: float | None = None,
    measured_E_tail_j: float | None = None,
    tail_horizon_s: float | None = None,
    plant_config_id: str | None = None,
    append_ledger: bool = True,
    refresh_drift: bool = False,
) -> dict[str, Any]:
    """Post-action accounting for ordinary Viv GPU speak. Never raises."""
    try:
        from lib.rid_electrical_action_accounting import account_gpu_inference
        from lib.rid_electrical_energy_ledger import append_action_row
        from lib.rid_electrical_predictor import PLANT_CONFIG_ID

        timings = timings_from_ollama_raw(raw)
        eval_s = timings.get("eval_duration_s")
        # Without plant Joules this is timing-only
        measurement_state = "measured" if measured_E_net_j is not None else "timing_only"
        aid = action_id or f"viv_speak_{uuid.uuid4().hex[:12]}"
        sid = session_id or "viv_ordinary"
        cfg = plant_config_id or PLANT_CONFIG_ID

        acct = account_gpu_inference(
            action_id=aid,
            model=str(model or "viv-voice"),
            eval_duration_s=float(eval_s) if eval_s is not None else None,
            measured_E_net_j=measured_E_net_j,
            actual_eval_tokens=timings.get("actual_eval_tokens"),
            session_id=sid,
            plant_config_id=cfg,
            residency_state=residency_state,
            action_type=action_type,
            refresh_drift=refresh_drift,
            append_drift_log=False,  # timing-only must not poison V1 drift RMSE
            prompt_eval_duration_s=timings.get("prompt_eval_duration_s"),
            measured_E_tail_j=measured_E_tail_j,
            tail_horizon_s=tail_horizon_s,
            unload_before=False,
            shadow_v2=False,
        )
        acct["measurement_state"] = measurement_state
        acct["at"] = _utc()
        if append_ledger:
            append_action_row(
                {
                    **acct,
                    "session_id": sid,
                    "executor": "gpu",
                    "measurement_state": measurement_state,
                }
            )
        return {
            "ok": True,
            "accounted": True,
            "action_id": aid,
            "measurement_state": measurement_state,
            "registry_selected_predictor": acct.get("registry_selected_predictor"),
            "predicted_E_j": acct.get("predicted_E_j"),
            "gates_action": False,
            "operational_authority": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": True,
            "accounted": False,
            "error": str(exc),
            "gates_action": False,
            "operational_authority": False,
            "silent": True,
        }


def maybe_record_from_speak_result(result: dict[str, Any]) -> dict[str, Any]:
    """Hook helper: record only on successful non-silent speak responses."""
    try:
        if not result or not result.get("ok") or result.get("silent"):
            return {"ok": True, "accounted": False, "reason": "silent_or_failed"}
        raw = result.get("raw")
        if not isinstance(raw, dict):
            return {"ok": True, "accounted": False, "reason": "no_raw"}
        mode = str(result.get("mode") or "generate")
        action_type = (
            "viv_speak_completion" if mode == "chat" else "viv_speak_generate"
        )
        return record_ordinary_gpu_action(
            model=result.get("model"),
            raw=raw,
            action_type=action_type,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": True,
            "accounted": False,
            "error": str(exc),
            "gates_action": False,
            "silent": True,
        }
