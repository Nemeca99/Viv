#!/usr/bin/env python3
"""Session/daily energy ledger aggregation for audited GPU actions."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from lib.paths import AUTO_ARTIFACTS

LEDGER_DIR = AUTO_ARTIFACTS / "rid_electrical" / "energy_ledger"
ACTIONS_JSONL = LEDGER_DIR / "actions.jsonl"
J_PER_KWH = 3.6e6

# Fields persisted on every accounting append (registry receipt contract)
RECEIPT_FIELDS = (
    "selected_predictor",
    "registry_selected_predictor",
    "selection_reason",
    "request_component",
    "predicted_E_j",
    "measured_E_j",
    "residual_j",
    "prediction_domain",
    "drift_state_v1",
    "drift_state_v2",
    "registry_release_id",
    "plant_config_id",
    "component_estimates",
    "confidence",
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def joules_to_kwh(e_j: float | None) -> float | None:
    if e_j is None:
        return None
    return float(e_j) / J_PER_KWH


def append_action_row(row: dict[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    """Append one accounting action to the ledger JSONL (full receipt fields)."""
    p = path or ACTIONS_JSONL
    p.parent.mkdir(parents=True, exist_ok=True)
    selected = row.get("selected_predictor")
    if selected is None:
        selected = row.get("registry_selected_predictor")
    measured_j = row.get("measured_E_j")
    if measured_j is None:
        measured_j = row.get("measured_energy")
    if measured_j is None:
        measured_j = row.get("measured_E_net_j")
    predicted_j = row.get("predicted_E_j")
    if predicted_j is None:
        predicted_j = row.get("predicted_E_net_j")
    residual = row.get("residual_j")
    if residual is None and predicted_j is not None and measured_j is not None:
        residual = float(measured_j) - float(predicted_j)

    out: dict[str, Any] = {
        "at": row.get("at") or _utc(),
        "action_id": row.get("action_id"),
        "session_id": row.get("session_id"),
        "action_type": row.get("action_type") or "gpu_inference",
        "model": row.get("model"),
        "executor": row.get("executor") or "gpu",
        "residency_state": row.get("residency_state"),
        "plant_config_id": row.get("plant_config_id"),
        "predicted_E_net_j": row.get("predicted_E_net_j"),
        "measured_E_net_j": row.get("measured_E_net_j"),
        "E_j": measured_j,  # authoritative measured for aggregates
        "eval_duration_s": row.get("eval_duration_s"),
        "actual_eval_tokens": row.get("actual_eval_tokens"),
        "drift_status": row.get("drift_status"),
        "predictor_state": row.get("predictor_state"),
        "E_kWh": joules_to_kwh(measured_j if isinstance(measured_j, (int, float)) else None),
        "operational_authority": False,
        "gates_action": False,
        # Registry receipt (must persist — previously dropped by whitelist)
        "selected_predictor": selected,
        "registry_selected_predictor": selected,
        "selection_reason": row.get("selection_reason"),
        "request_component": row.get("request_component"),
        "predicted_E_j": predicted_j,
        "measured_E_j": measured_j,
        "residual_j": residual,
        "prediction_domain": row.get("prediction_domain"),
        "drift_state_v1": row.get("drift_state_v1"),
        "drift_state_v2": row.get("drift_state_v2"),
        "registry_release_id": row.get("registry_release_id"),
        "component_estimates": row.get("component_estimates"),
        "confidence": row.get("confidence"),
        "measurement_state": row.get("measurement_state"),
    }
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out


def load_actions(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or ACTIONS_JSONL
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _sum_energy(rows: Sequence[dict[str, Any]]) -> float:
    total = 0.0
    for r in rows:
        e = r.get("E_j")
        if e is None:
            e = r.get("measured_E_j")
        if e is None:
            continue
        try:
            total += float(e)
        except (TypeError, ValueError):
            continue
    return total


def _sum_field(rows: Sequence[dict[str, Any]], key: str) -> float:
    total = 0.0
    for r in rows:
        comps = r.get("component_estimates") or {}
        v = r.get(key)
        if v is None and isinstance(comps, dict):
            # map predicted component keys
            alias = {
                "E_load_j": "E_load_j",
                "E_prompt_j": "E_prompt_j",
                "E_eval_j": "E_eval_j",
                "E_tail_j": "E_tail_j",
            }.get(key)
            if alias:
                v = comps.get(alias)
        if v is None:
            continue
        try:
            total += float(v)
        except (TypeError, ValueError):
            continue
    return total


def _breakdown(rows: Sequence[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        buckets[str(r.get(key) or "unknown")].append(r)
    out: dict[str, dict[str, Any]] = {}
    for k, rs in buckets.items():
        e = _sum_energy(rs)
        pred = _sum_field(rs, "predicted_E_j")
        resid = _sum_field(rs, "residual_j")
        out[k] = {
            "n": len(rs),
            "E_j": e,
            "E_kWh": joules_to_kwh(e),
            "predicted_E_j": pred,
            "residual_j": resid,
        }
    return out


def _null_stats(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    null_sel = sum(
        1
        for r in rows
        if r.get("registry_selected_predictor") is None
        and r.get("selected_predictor") is None
    )
    rejected = sum(
        1
        for r in rows
        if str(r.get("confidence") or "") == "rejected_stratum"
        or str(r.get("selection_reason") or "").startswith("rejected_stratum")
        or str(r.get("request_component") or "") in {"tail_5", "warm_prompt_eval"}
    )
    return {
        "n": n,
        "null_selected": null_sel,
        "null_rate": (null_sel / n) if n else None,
        "rejected_stratum_requests": rejected,
    }


def summarize_sessions(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_session[str(r.get("session_id") or "unknown")].append(r)
    sessions = []
    for sid, rs in sorted(by_session.items()):
        e = _sum_energy(rs)
        sessions.append(
            {
                "session_id": sid,
                "n_actions": len(rs),
                "E_session_j": e,
                "E_session_kWh": joules_to_kwh(e),
                "by_action_type": _breakdown(rs, "action_type"),
                "by_model": _breakdown(rs, "model"),
                "by_residency": _breakdown(rs, "residency_state"),
                "by_executor": _breakdown(rs, "executor"),
                "by_registry_selected_predictor": _breakdown(
                    rs, "registry_selected_predictor"
                ),
                "by_registry_release_id": _breakdown(rs, "registry_release_id"),
                "null_stats": _null_stats(rs),
                "component_predicted_totals": {
                    "E_load_j": _sum_field(rs, "E_load_j"),
                    "E_prompt_j": _sum_field(rs, "E_prompt_j"),
                    "E_eval_j": _sum_field(rs, "E_eval_j"),
                    "E_tail_j": _sum_field(rs, "E_tail_j"),
                },
            }
        )
    return {
        "ok": True,
        "at": _utc(),
        "n_sessions": len(sessions),
        "n_actions": len(rows),
        "E_total_j": _sum_energy(rows),
        "sessions": sessions,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
        },
    }


def summarize_daily(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        at = str(r.get("at") or "")
        day = at[:10] if len(at) >= 10 else "unknown"
        by_day[day].append(r)
    days = []
    for day, rs in sorted(by_day.items()):
        sess = summarize_sessions(rs)
        e_day = _sum_energy(rs)
        days.append(
            {
                "date": day,
                "n_actions": len(rs),
                "n_sessions": sess.get("n_sessions"),
                "E_daily_j": e_day,
                "E_daily_kWh": joules_to_kwh(e_day),
                "by_action_type": _breakdown(rs, "action_type"),
                "by_model": _breakdown(rs, "model"),
                "by_residency": _breakdown(rs, "residency_state"),
                "by_executor": _breakdown(rs, "executor"),
                "by_registry_selected_predictor": _breakdown(
                    rs, "registry_selected_predictor"
                ),
                "by_registry_release_id": _breakdown(rs, "registry_release_id"),
                "null_stats": _null_stats(rs),
                "component_predicted_totals": {
                    "E_load_j": _sum_field(rs, "E_load_j"),
                    "E_prompt_j": _sum_field(rs, "E_prompt_j"),
                    "E_eval_j": _sum_field(rs, "E_eval_j"),
                    "E_tail_j": _sum_field(rs, "E_tail_j"),
                },
                "sessions": sess.get("sessions"),
            }
        )
    return {
        "ok": True,
        "at": _utc(),
        "n_days": len(days),
        "n_actions": len(rows),
        "days": days,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
        },
    }


def summarize_registry_accounting(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Registry-focused energy accounting report."""
    e = _sum_energy(rows)
    pred = _sum_field(rows, "predicted_E_j")
    resid = _sum_field(rows, "residual_j")
    full_receipt = 0
    for r in rows:
        if all(
            r.get(k) is not None
            for k in (
                "registry_selected_predictor",
                "selection_reason",
                "registry_release_id",
                "plant_config_id",
            )
        ) or (
            r.get("registry_selected_predictor") is None
            and r.get("selection_reason") is not None
            and r.get("registry_release_id") is not None
            and r.get("plant_config_id") is not None
        ):
            # null selection still counts if reason + release + plant present
            if r.get("selection_reason") and r.get("registry_release_id") and r.get(
                "plant_config_id"
            ):
                full_receipt += 1
    n = len(rows)
    return {
        "ok": True,
        "at": _utc(),
        "n_actions": n,
        "E_j": e,
        "E_kWh": joules_to_kwh(e),
        "predicted_E_j": pred,
        "residual_j": resid,
        "by_model": _breakdown(rows, "model"),
        "by_action_type": _breakdown(rows, "action_type"),
        "by_residency_state": _breakdown(rows, "residency_state"),
        "by_registry_selected_predictor": _breakdown(rows, "registry_selected_predictor"),
        "by_registry_release_id": _breakdown(rows, "registry_release_id"),
        "by_request_component": _breakdown(rows, "request_component"),
        "component_predicted_totals": {
            "E_load_j": _sum_field(rows, "E_load_j"),
            "E_prompt_j": _sum_field(rows, "E_prompt_j"),
            "E_eval_j": _sum_field(rows, "E_eval_j"),
            "E_tail_j": _sum_field(rows, "E_tail_j"),
        },
        "null_stats": _null_stats(rows),
        "receipt_completeness": {
            "n_full": full_receipt,
            "n": n,
            "rate": (full_receipt / n) if n else None,
        },
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "gates_action": False,
        },
    }
