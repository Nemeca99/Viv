#!/usr/bin/env python3
"""Read-only V2 shadow logging alongside V1 accounting (no authority)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_predictor_v2 import load_candidate, predict_E_action

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
SHADOW_LOG = OUT / "predictor_v2_shadow_log.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_v2_shadow_row(row: dict[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else SHADOW_LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def shadow_account_v2(
    *,
    action_id: str,
    session_id: str | None,
    t_eval_s: float | None,
    t_prompt_s: float | None,
    tail_horizon_s: float,
    residency: str,
    unload_before: bool = False,
    measured_E_net_j: float | None,
    measured_E_tail_j: float | None,
    plant_config_id: str | None = None,
    append: bool = True,
) -> dict[str, Any]:
    """Record V2 estimate vs measured action energy. Never gates actions."""
    cand = load_candidate()
    if not cand.get("loaded"):
        return {
            "ok": False,
            "shadowed": False,
            "reason": "candidate_missing",
            "operational_authority": False,
            "accounting_predictor_v2_approved": False,
        }
    if t_eval_s is None:
        return {
            "ok": False,
            "shadowed": False,
            "reason": "missing_t_eval",
            "operational_authority": False,
            "accounting_predictor_v2_approved": False,
        }
    pred = predict_E_action(
        t_eval_s=float(t_eval_s),
        t_prompt_s=float(t_prompt_s or 0.0),
        tail_horizon_s=float(tail_horizon_s),
        residency=residency,
        unload_before=unload_before,
        plant_config_id=plant_config_id,
    )
    e_meas = None
    if measured_E_net_j is not None and measured_E_tail_j is not None:
        e_meas = float(measured_E_net_j) + float(measured_E_tail_j)
    e_hat = pred.get("predicted_E_action_j")
    resid = None if e_meas is None or e_hat is None else float(e_meas) - float(e_hat)
    row = {
        "at": _utc(),
        "action_id": action_id,
        "session_id": session_id,
        "predictor_version": pred.get("predictor_version"),
        "predicted_E_action_j": e_hat,
        "predicted_E_net_j": pred.get("predicted_E_net_j"),
        "measured_E_action_j": e_meas,
        "measured_E_net_j": measured_E_net_j,
        "measured_E_tail_j": measured_E_tail_j,
        "residual_j": resid,
        "t_eval_s": t_eval_s,
        "t_prompt_s": t_prompt_s,
        "tail_horizon_s": tail_horizon_s,
        "residency": residency,
        "confidence": pred.get("confidence"),
        "empirical_error_scale_j": pred.get("empirical_error_scale_j"),
        "v1_fallback_approved": True,
        "accounting_predictor_v2_approved": False,
        "operational_authority": False,
        "master_routing_authorized": False,
        "auto_admit": False,
        "gates_action": False,
    }
    if append and pred.get("confidence") == "ok":
        append_v2_shadow_row(row)
        row["shadowed"] = True
    else:
        row["shadowed"] = False
    row["ok"] = True
    return row
