#!/usr/bin/env python3
"""Live accounting drift checks for the approved eval_duration predictor.

Records predicted-vs-actual residuals. Issues a live verdict only when
usable n >= MIN_LIVE_N. Never grants operational/Master/routing authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_predictor import (
    DOMAIN_MAX_S,
    DOMAIN_MIN_S,
    HELD_OUT_RMSE_J,
    PLANT_CONFIG_ID,
    PREDICTOR_VERSION,
    predict_E_net,
)

DRIFT_LOG_PATH = (
    AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign" / "predictor_drift_log.jsonl"
)

MIN_LIVE_N = 20
DRIFT_RMSE_MULT = 1.5
V1_SPECIALTY_RESIDENCY = "warm_repeat"
_EXCLUDED_CONFIDENCE = frozenset(
    {
        "config_mismatch",
        "invalid_input",
        "out_of_validated_domain",
        "predictor_stale_revalidation_required",
    }
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_revalidation_fingerprint(
    *,
    plant_config_id: str = PLANT_CONFIG_ID,
    model: str = "viv-voice-qwen",
    residency: str = "warm_repeat",
    baseline_recipe: str = "settled_8s_window",
    telemetry_cadence_s: float = 0.1,
    predictor_version: str = PREDICTOR_VERSION,
) -> str:
    """Stable fingerprint of locked plant/predictor configuration."""
    payload = {
        "plant_config_id": plant_config_id,
        "model": model,
        "residency": residency,
        "baseline_recipe": baseline_recipe,
        "telemetry_cadence_s": float(telemetry_cadence_s),
        "predictor_version": predictor_version,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


LOCKED_REVALIDATION_FINGERPRINT = make_revalidation_fingerprint()


def record_accounting_use(
    eval_duration_s: float,
    measured_E_net_j: float,
    *,
    session_id: str,
    plant_config_id: str | None = None,
    gpu_temp_settle_c: float | None = None,
    residency: str = "warm_repeat",
    revalidation_fingerprint: str | None = None,
    append: bool = True,
) -> dict[str, Any]:
    """Create (and optionally append) one live accounting observation."""
    cfg = plant_config_id if plant_config_id is not None else PLANT_CONFIG_ID
    pred = predict_E_net(eval_duration_s, plant_config_id=cfg)
    predicted = pred.get("predicted_E_net_j")
    residual = (
        float(measured_E_net_j) - float(predicted)
        if predicted is not None
        else None
    )
    fp = revalidation_fingerprint or make_revalidation_fingerprint(
        plant_config_id=str(cfg),
        residency=str(residency),
    )
    rec = {
        "at": _utc(),
        "session_id": str(session_id),
        "eval_duration_s": float(eval_duration_s),
        "measured_E_net_j": float(measured_E_net_j),
        "predicted_E_net_j": predicted,
        "residual_j": residual,
        "abs_residual_j": abs(float(residual)) if residual is not None else None,
        "plant_config_id": str(cfg),
        "gpu_temp_settle_c": gpu_temp_settle_c,
        "residency": str(residency),
        "revalidation_fingerprint": fp,
        "confidence": pred.get("confidence"),
        "in_domain": pred.get("in_domain"),
        "heldout_rmse_j": pred.get("heldout_rmse_j"),
        "operational_authority": False,
        "master_routing_authorized": False,
        "auto_admit": False,
    }
    if append:
        DRIFT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DRIFT_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def classify_drift_record(r: dict[str, Any]) -> tuple[bool, str]:
    """Return (eligible, reason). Timing-only and non-warm never grade V1 RMSE."""
    if r.get("measurement_state") == "timing_only":
        return False, "timing_only"
    meas = r.get("measured_E_net_j")
    if meas is None:
        return False, "missing_measured_E_net"
    try:
        mv = float(meas)
    except (TypeError, ValueError):
        return False, "non_numeric_measured_E_net"
    if not math.isfinite(mv):
        return False, "non_finite_measured_E_net"

    te = r.get("eval_duration_s")
    try:
        tev = float(te) if te is not None else None
    except (TypeError, ValueError):
        return False, "invalid_eval_duration"
    if tev is None or not (DOMAIN_MIN_S <= tev <= DOMAIN_MAX_S):
        return False, "out_of_domain_duration"
    if not r.get("in_domain", True):
        # Prefer explicit in_domain=False; duration check above is authoritative
        if r.get("in_domain") is False:
            return False, "out_of_domain_flag"

    residency = str(r.get("residency") or r.get("residency_state") or "")
    if residency != V1_SPECIALTY_RESIDENCY:
        return False, "non_warm_residency"

    if str(r.get("plant_config_id") or "") != PLANT_CONFIG_ID:
        return False, "config_mismatch"

    conf = str(r.get("confidence") or "")
    if conf in _EXCLUDED_CONFIDENCE:
        return False, f"confidence:{conf}"

    fp = r.get("revalidation_fingerprint")
    if fp is not None and str(fp) and str(fp) != LOCKED_REVALIDATION_FINGERPRINT:
        # Allow fingerprints that differ only because residency was stamped into fp
        # for warm specialty rows recorded with warm_repeat — locked fp uses warm_repeat
        expected_warm = make_revalidation_fingerprint(
            plant_config_id=PLANT_CONFIG_ID,
            residency=V1_SPECIALTY_RESIDENCY,
        )
        if str(fp) != expected_warm and str(fp) != LOCKED_REVALIDATION_FINGERPRINT:
            return False, "fingerprint_mismatch"

    resid = r.get("residual_j")
    if resid is None:
        return False, "missing_residual"
    try:
        rv = float(resid)
    except (TypeError, ValueError):
        return False, "non_numeric_residual"
    if not math.isfinite(rv):
        return False, "non_finite_residual"
    return True, "eligible"


def _usable_records(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in records:
        # Bare residual-only dicts (unit helpers): keep legacy path via compute_drift_summary
        if "residual_j" in r and "measured_E_net_j" not in r and "residency" not in r:
            try:
                rv = float(r["residual_j"])
            except (TypeError, ValueError):
                continue
            if math.isfinite(rv):
                out.append(r)
            continue
        ok, _reason = classify_drift_record(r)
        if ok:
            out.append(r)
    return out


def audit_drift_eligibility(
    records: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classify every drift row; compare pooled vs eligible RMSE."""
    rows = list(records) if records is not None else load_drift_log()
    by_reason: dict[str, int] = {}
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for r in rows:
        ok, reason = classify_drift_record(r)
        by_reason[reason] = by_reason.get(reason, 0) + 1
        if ok:
            eligible.append(r)
        else:
            excluded.append({"reason": reason, "session_id": r.get("session_id"), "at": r.get("at")})

    def _rmse(rs: list[dict[str, Any]]) -> float | None:
        errs = []
        for r in rs:
            try:
                errs.append(float(r["residual_j"]))
            except (TypeError, ValueError, KeyError):
                continue
        if not errs:
            return None
        return math.sqrt(statistics.fmean([e * e for e in errs]))

    # Pooled = old semantics (in_domain + plant + residual only)
    pooled = []
    for r in rows:
        if not r.get("in_domain", True) and r.get("in_domain") is False:
            continue
        if str(r.get("plant_config_id") or "") != PLANT_CONFIG_ID:
            continue
        if r.get("residual_j") is None:
            continue
        try:
            float(r["residual_j"])
        except (TypeError, ValueError):
            continue
        pooled.append(r)

    speech_n = sum(
        1
        for r in rows
        if "viv_speak" in str(r.get("session_id") or "")
        or str(r.get("action_type") or "").startswith("viv_speak")
        or r.get("measurement_state") == "timing_only"
    )
    thr = DRIFT_RMSE_MULT * float(HELD_OUT_RMSE_J)
    elig_rmse = _rmse(eligible)
    return {
        "ok": True,
        "at": _utc(),
        "n_total": len(rows),
        "n_eligible": len(eligible),
        "n_excluded": len(excluded),
        "by_reason": by_reason,
        "speech_contamination_n": speech_n,
        "speech_contaminated": speech_n > 0,
        "pooled_legacy_n": len(pooled),
        "pooled_legacy_rmse_j": _rmse(pooled),
        "eligible_rmse_j": elig_rmse,
        "drift_alert_threshold_j": thr,
        "eligible_passes_gate": (
            len(eligible) >= MIN_LIVE_N
            and elig_rmse is not None
            and elig_rmse <= thr
        ),
        "min_live_n": MIN_LIVE_N,
        "note": (
            "Timing-only and non-warm residency must not grade V1 RMSE. "
            "No operational authority."
        ),
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "auto_refit": False,
        },
    }


def compute_drift_summary(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Summarize residual drift (legacy helper; no n-gate verdict)."""
    usable = _usable_records(records)
    # Fall back to raw residual list for unit tests that pass bare residuals.
    if not usable and records:
        residuals = []
        for r in records:
            if "residual_j" not in r:
                continue
            try:
                rv = float(r["residual_j"])
            except (TypeError, ValueError):
                continue
            if math.isfinite(rv):
                residuals.append(rv)
    else:
        residuals = [float(r["residual_j"]) for r in usable]

    thr = DRIFT_RMSE_MULT * float(HELD_OUT_RMSE_J)
    if not residuals:
        return {
            "n": 0,
            "mean_residual_j": None,
            "rmse_j": None,
            "max_abs_residual_j": None,
            "drift_alert_threshold_j": thr,
            "drift_alert": False,
            "note": "No usable residuals.",
        }
    rmse = math.sqrt(statistics.fmean([r * r for r in residuals]))
    return {
        "n": len(residuals),
        "mean_residual_j": statistics.fmean(residuals),
        "rmse_j": rmse,
        "max_abs_residual_j": max(abs(r) for r in residuals),
        "drift_alert_threshold_j": thr,
        "drift_alert": bool(rmse > thr),
        "note": "Report only. No operational authority granted.",
    }


def evaluate_live_accounting(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Issue live accounting lifecycle verdict with n>=20 gate."""
    usable = _usable_records(records)
    # Prefer eligible specialty records only (no bare-residual fallback for plant logs)
    plantish = any("measured_E_net_j" in r or "residency" in r for r in records)
    if plantish:
        summary = compute_drift_summary(usable)
        # Force empty summary semantics when no eligible plant rows
        if not usable:
            summary = {
                "n": 0,
                "mean_residual_j": None,
                "rmse_j": None,
                "max_abs_residual_j": None,
                "drift_alert_threshold_j": DRIFT_RMSE_MULT * float(HELD_OUT_RMSE_J),
                "drift_alert": False,
                "note": "No eligible V1 specialty residuals.",
            }
    else:
        summary = compute_drift_summary(usable if usable else records)
    n = int(summary.get("n") or 0)
    thr = float(summary["drift_alert_threshold_j"])
    rmse = summary.get("rmse_j")

    if n < MIN_LIVE_N:
        status = "insufficient_live_sample"
        stale = False
        validated = False
    elif rmse is not None and float(rmse) <= thr:
        status = "live_accounting_validated"
        stale = False
        validated = True
    else:
        status = "predictor_stale_revalidation_required"
        stale = True
        validated = False

    return {
        "ok": True,
        "status": status,
        "n_usable": n,
        "min_live_n": MIN_LIVE_N,
        "rmse_live_j": rmse,
        "heldout_rmse_j": HELD_OUT_RMSE_J,
        "drift_alert_threshold_j": thr,
        "mean_residual_j": summary.get("mean_residual_j"),
        "max_abs_residual_j": summary.get("max_abs_residual_j"),
        "live_accounting_validated": validated,
        "predictor_stale": stale,
        "plant_config_id": PLANT_CONFIG_ID,
        "locked_revalidation_fingerprint": LOCKED_REVALIDATION_FINGERPRINT,
        "operational_authority": False,
        "master_routing_authorized": False,
        "auto_admit": False,
        "note": (
            "Live accounting validation only (warm_repeat + measured E_net). "
            "No Master/routing/operational authority."
        ),
    }


def refresh_and_apply_drift_status() -> dict[str, Any]:
    """Recompute live drift from log and apply policy stale/validated flags.

    When stale, estimates must be refused by callers; actions are never gated.
    """
    from lib.rid_electrical_policy import apply_live_accounting_verdict

    verdict = evaluate_live_accounting(load_drift_log())
    apply_live_accounting_verdict(str(verdict.get("status") or ""))
    return {
        **verdict,
        "estimates_refused": bool(verdict.get("predictor_stale")),
        "refit_forbidden": True,
        "gates_action": False,
    }


def load_drift_log(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or DRIFT_LOG_PATH
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
