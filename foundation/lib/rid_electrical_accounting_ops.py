#!/usr/bin/env python3
"""Production accounting operations: status, passive drift, config-mismatch.

Never gates actions. Never auto-refits. Drift/plant mismatch → separate review flag only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_accounting_registry_release import (
    RELEASE_ID,
    RELEASE_PATH,
    assert_release_intact,
    load_registry_release,
)
from lib.rid_electrical_drift_check import refresh_and_apply_drift_status
from lib.rid_electrical_energy_ledger import (
    LEDGER_DIR,
    load_actions,
    summarize_daily,
    summarize_registry_accounting,
    summarize_sessions,
)
from lib.rid_electrical_policy import (
    apply_accounting_ops_verdict,
    policy_stamp,
)
from lib.rid_electrical_v2_drift import evaluate_v2_drift

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
OPS_STATUS_JSON = CAMPAIGN / "PRODUCTION_ACCOUNTING_OPS_STATUS.json"
OPS_STATUS_MD = CAMPAIGN / "PRODUCTION_ACCOUNTING_OPS_STATUS.md"
OPS_DRIFT_JSON = CAMPAIGN / "ops_drift_latest.json"
OPS_DRIFT_MD = CAMPAIGN / "ops_drift_latest.md"
OPS_MISMATCH_JSON = CAMPAIGN / "ops_config_mismatch_latest.json"
OPS_MISMATCH_MD = CAMPAIGN / "ops_config_mismatch_latest.md"
HEALTH_JSON = CAMPAIGN / "registry_health_latest.json"

MISMATCH_WINDOW = 50
MISMATCH_BURST_THRESHOLD = 3


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json_md(path_json: Path, path_md: Path, payload: dict[str, Any], title: str) -> None:
    path_json.parent.mkdir(parents=True, exist_ok=True)
    path_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"# {title}", "", f"- at: `{payload.get('at')}`", ""]
    for k, v in payload.items():
        if k in {"at", "policy", "authority"}:
            continue
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    path_md.write_text("\n".join(lines), encoding="utf-8")


def scan_config_mismatch(
    rows: Sequence[dict[str, Any]],
    *,
    window: int = MISMATCH_WINDOW,
) -> dict[str, Any]:
    """Count config_mismatch in the most recent `window` rows."""
    recent = list(rows)[-int(window) :]
    mismatches = []
    numeric_attempts = []
    for r in recent:
        reason = str(r.get("selection_reason") or "")
        conf = str(r.get("confidence") or "")
        is_mm = reason == "config_mismatch" or conf == "config_mismatch"
        if is_mm:
            mismatches.append(r)
        # numeric attempt: had a selected predictor or predicted value
        if (
            r.get("registry_selected_predictor") in {"V1", "V2"}
            or r.get("predicted_E_j") is not None
            or is_mm
        ):
            numeric_attempts.append(r)
    n_mm = len(mismatches)
    burst = n_mm >= MISMATCH_BURST_THRESHOLD
    return {
        "ok": True,
        "at": _utc(),
        "window": int(window),
        "n_recent": len(recent),
        "n_numeric_attempts": len(numeric_attempts),
        "config_mismatch_count": n_mm,
        "config_mismatch_rate": (n_mm / len(recent)) if recent else None,
        "burst": burst,
        "burst_threshold": MISMATCH_BURST_THRESHOLD,
        "note": "Burst opens ops_review_required only; never auto-refit.",
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "gates_action": False,
        },
    }


def ledger_window_stats(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    null_n = sum(
        1
        for r in rows
        if r.get("registry_selected_predictor") is None
        and r.get("selected_predictor") is None
    )
    measured_n = sum(
        1
        for r in rows
        if r.get("measured_E_j") is not None
        or (
            r.get("measured_E_net_j") is not None
            and r.get("measurement_state") != "timing_only"
        )
    )
    timing_n = sum(1 for r in rows if r.get("measurement_state") == "timing_only")
    return {
        "n_receipts_window": n,
        "null_selected": null_n,
        "null_rate": (null_n / n) if n else None,
        "measurement_coverage": {
            "measured": measured_n,
            "timing_only": timing_n,
            "rate_measured": (measured_n / n) if n else None,
        },
    }


def refresh_aggregates() -> dict[str, Any]:
    rows = load_actions()
    session = summarize_sessions(rows)
    daily = summarize_daily(rows)
    registry = summarize_registry_accounting(rows)
    stamp = policy_stamp()
    session["policy"] = stamp
    daily["policy"] = stamp
    registry["policy"] = stamp
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    s_json = LEDGER_DIR / "energy_ledger_session_latest.json"
    d_json = LEDGER_DIR / "energy_ledger_daily_latest.json"
    r_json = LEDGER_DIR / "registry_accounting_report_latest.json"
    s_json.write_text(json.dumps(session, indent=2), encoding="utf-8")
    d_json.write_text(json.dumps(daily, indent=2), encoding="utf-8")
    r_json.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    return {
        "n_actions": len(rows),
        "session": str(s_json).replace("\\", "/"),
        "daily": str(d_json).replace("\\", "/"),
        "registry": str(r_json).replace("\\", "/"),
    }


def run_passive_monitor(*, apply_ops_status: bool = True) -> dict[str, Any]:
    """Passive V1/V2 drift + config-mismatch + aggregates. No coeff writes."""
    v1 = refresh_and_apply_drift_status()
    v2 = evaluate_v2_drift(apply_policy=True)
    rows = load_actions()
    mismatch = scan_config_mismatch(rows)
    stats = ledger_window_stats(rows)
    agg = refresh_aggregates()

    review_reasons: list[str] = []
    if v1.get("predictor_stale") or str(v1.get("status") or "") == (
        "predictor_stale_revalidation_required"
    ):
        review_reasons.append("v1_stale")
    if str(v2.get("status") or "") == "v2_stale_revalidation_required":
        review_reasons.append("v2_stale")
    if mismatch.get("burst"):
        review_reasons.append("config_mismatch_burst")

    ops_review_required = len(review_reasons) > 0
    review_reason = ",".join(review_reasons) if review_reasons else None

    release_id = RELEASE_ID
    try:
        release_id = str(load_registry_release().get("release_id") or RELEASE_ID)
    except Exception:  # noqa: BLE001
        pass

    # Preserve promoted ops status if already operations; else incomplete until bootstrap
    prior_status = "production_accounting_operations_incomplete"
    if OPS_STATUS_JSON.exists():
        try:
            prior = json.loads(OPS_STATUS_JSON.read_text(encoding="utf-8"))
            if prior.get("status") == "production_accounting_operations":
                prior_status = "production_accounting_operations"
        except Exception:  # noqa: BLE001
            pass

    status = prior_status
    drift_payload = {
        "ok": True,
        "at": _utc(),
        "drift_v1": v1,
        "drift_v2": v2,
        "ops_review_required": ops_review_required,
        "review_reason": review_reason,
        "auto_refit": False,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "gates_action": False,
        },
    }
    _write_json_md(OPS_DRIFT_JSON, OPS_DRIFT_MD, drift_payload, "Ops drift")
    _write_json_md(
        OPS_MISMATCH_JSON, OPS_MISMATCH_MD, mismatch, "Ops config mismatch"
    )

    ops_status = {
        "ok": True,
        "at": _utc(),
        "status": status,
        "release_id": release_id,
        "drift_v1": {
            "status": v1.get("status"),
            "predictor_stale": v1.get("predictor_stale"),
        },
        "drift_v2": {"status": v2.get("status")},
        "config_mismatch_count": mismatch.get("config_mismatch_count"),
        "null_rate": stats.get("null_rate"),
        "n_receipts_window": stats.get("n_receipts_window"),
        "measurement_coverage": stats.get("measurement_coverage"),
        "ops_review_required": ops_review_required,
        "review_reason": review_reason,
        "aggregates": agg,
        "artifacts": {
            "ops_status": str(OPS_STATUS_JSON).replace("\\", "/"),
            "ops_drift": str(OPS_DRIFT_JSON).replace("\\", "/"),
            "ops_config_mismatch": str(OPS_MISMATCH_JSON).replace("\\", "/"),
        },
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "gates_action": False,
        },
        "policy": policy_stamp(),
    }
    if apply_ops_status:
        _write_json_md(
            OPS_STATUS_JSON, OPS_STATUS_MD, ops_status, "Production accounting ops"
        )
        apply_accounting_ops_verdict(
            status=status,
            ops_review_required=ops_review_required,
            review_reason=review_reason,
        )
    return ops_status


def evaluate_ops_bootstrap_gates() -> dict[str, Any]:
    """Pre-locked bootstrap gates for production_accounting_operations."""
    gates: dict[str, Any] = {}

    release_ok = RELEASE_PATH.exists()
    health_ok = False
    if HEALTH_JSON.exists():
        try:
            h = json.loads(HEALTH_JSON.read_text(encoding="utf-8"))
            health_ok = h.get("status") == "production_accounting_registry_validated"
        except Exception:  # noqa: BLE001
            health_ok = False
    gates["registry_release_and_health"] = {
        "pass": release_ok and health_ok,
        "release_present": release_ok,
        "health_validated": health_ok,
    }

    hook_ok = False
    try:
        from lib.rid_electrical_ops_hook import record_ordinary_gpu_action

        hook_ok = callable(record_ordinary_gpu_action)
    except Exception:  # noqa: BLE001
        hook_ok = False
    gates["ops_hook_importable"] = {"pass": hook_ok}

    artifacts_ok = all(
        p.exists() for p in (OPS_STATUS_JSON, OPS_DRIFT_JSON, OPS_MISMATCH_JSON)
    )
    gates["monitor_artifacts"] = {
        "pass": artifacts_ok,
        "ops_status": OPS_STATUS_JSON.exists(),
        "ops_drift": OPS_DRIFT_JSON.exists(),
        "ops_config_mismatch": OPS_MISMATCH_JSON.exists(),
    }

    intact = assert_release_intact()
    gates["release_hashes_intact"] = {
        "pass": bool(intact.get("ok")),
        "mismatches": intact.get("mismatches") or [],
    }

    stamp = policy_stamp()
    authority_ok = (
        stamp.get("master_weight_enabled") is False
        and stamp.get("advisory_routing_enabled") is False
        and stamp.get("admission_granted") is False
    )
    gates["authority_closed"] = {"pass": authority_ok}

    all_pass = all(bool(g.get("pass")) for g in gates.values())
    return {
        "ok": True,
        "at": _utc(),
        "all_gates_pass": all_pass,
        "gates": gates,
    }


def promote_ops_status() -> dict[str, Any]:
    """Run monitor then promote if bootstrap gates pass."""
    monitor = run_passive_monitor(apply_ops_status=True)
    boot = evaluate_ops_bootstrap_gates()
    if not boot.get("all_gates_pass"):
        status = "production_accounting_operations_incomplete"
        payload = {
            **monitor,
            "status": status,
            "bootstrap": boot,
            "at": _utc(),
        }
        _write_json_md(
            OPS_STATUS_JSON, OPS_STATUS_MD, payload, "Production accounting ops"
        )
        apply_accounting_ops_verdict(
            status=status,
            ops_review_required=bool(monitor.get("ops_review_required")),
            review_reason=monitor.get("review_reason"),
        )
        return payload

    status = "production_accounting_operations"
    payload = {
        **monitor,
        "status": status,
        "bootstrap": boot,
        "at": _utc(),
    }
    # Preserve review flag from monitor
    _write_json_md(
        OPS_STATUS_JSON, OPS_STATUS_MD, payload, "Production accounting ops"
    )
    apply_accounting_ops_verdict(
        status=status,
        ops_review_required=bool(monitor.get("ops_review_required")),
        review_reason=monitor.get("review_reason"),
    )
    payload["policy"] = policy_stamp()
    return payload
