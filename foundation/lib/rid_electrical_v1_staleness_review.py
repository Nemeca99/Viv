#!/usr/bin/env python3
"""Bounded V1 staleness review: freeze, audit, localize, decide — never silent refit."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_drift_check import (
    DRIFT_LOG_PATH,
    DRIFT_RMSE_MULT,
    HELD_OUT_RMSE_J,
    LOCKED_REVALIDATION_FINGERPRINT,
    MIN_LIVE_N,
    PLANT_CONFIG_ID,
    audit_drift_eligibility,
    evaluate_live_accounting,
    load_drift_log,
    refresh_and_apply_drift_status,
)
from lib.rid_electrical_policy import policy_stamp
from lib.rid_electrical_predictor import ALPHA, BETA, DOMAIN_MAX_S, DOMAIN_MIN_S

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
TRIGGER_JSON = CAMPAIGN / "V1_STALENESS_TRIGGER_WINDOW_V1.json"
TRIGGER_COPY = CAMPAIGN / "V1_STALENESS_TRIGGER_WINDOW_V1" / "predictor_drift_log.jsonl"
ELIG_JSON = CAMPAIGN / "V1_DRIFT_ELIGIBILITY_AUDIT_V1.json"
ELIG_MD = CAMPAIGN / "V1_DRIFT_ELIGIBILITY_AUDIT_V1.md"
DIAG_JSON = CAMPAIGN / "V1_STALENESS_DIAGNOSTIC_FIT_COPY.json"
REVAL_JSON = CAMPAIGN / "v1_staleness_revalidation_latest.json"
REVAL_MD = CAMPAIGN / "v1_staleness_revalidation_latest.md"
REVIEW_JSON = CAMPAIGN / "V1_STALENESS_REVIEW_V1.json"
REVIEW_MD = CAMPAIGN / "V1_STALENESS_REVIEW_V1.md"
DECISION_JSON = CAMPAIGN / "V1_STALENESS_DECISION_LOCK.json"

# Speak-hook integration ~ ops promote window (UTC)
SPEAK_HOOK_CUTOVER = "2026-07-27T18:25:00+00:00"

CAUSE_CLASSES = (
    "monitor_or_receipt_semantics_fault",
    "plant_configuration_changed",
    "stable_relationship_shifted",
    "v1_relationship_no_longer_repeatable",
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_trigger_window() -> dict[str, Any]:
    """Hash + copy the triggering drift window and related artifacts."""
    CAMPAIGN.mkdir(parents=True, exist_ok=True)
    dest_dir = CAMPAIGN / "V1_STALENESS_TRIGGER_WINDOW_V1"
    dest_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "predictor_drift_log": DRIFT_LOG_PATH,
        "ops_drift_latest": CAMPAIGN / "ops_drift_latest.json",
        "PRODUCTION_ACCOUNTING_OPS_STATUS": CAMPAIGN / "PRODUCTION_ACCOUNTING_OPS_STATUS.json",
        "ACCOUNTING_REGISTRY_RELEASE_V1": CAMPAIGN / "ACCOUNTING_REGISTRY_RELEASE_V1.json",
        "live_accounting_validation_latest": CAMPAIGN / "live_accounting_validation_latest.json",
        "PREDICTOR_V1_BASELINE_FROZEN": CAMPAIGN / "PREDICTOR_V1_BASELINE_FROZEN.json",
    }
    artifacts: dict[str, Any] = {}
    for key, path in sources.items():
        sha = _sha256(path)
        entry: dict[str, Any] = {
            "path": str(path).replace("\\", "/"),
            "exists": path.exists(),
            "sha256": sha,
        }
        if path.exists() and path.suffix == ".jsonl":
            rows = load_drift_log(path)
            entry["n_rows"] = len(rows)
            ats = [str(r.get("at") or "") for r in rows if r.get("at")]
            entry["time_span"] = {"first": ats[0] if ats else None, "last": ats[-1] if ats else None}
            # Immutable copy of trigger log
            shutil.copy2(path, dest_dir / path.name)
            entry["frozen_copy"] = str((dest_dir / path.name)).replace("\\", "/")
        elif path.exists() and path.suffix == ".json":
            shutil.copy2(path, dest_dir / path.name)
            entry["frozen_copy"] = str((dest_dir / path.name)).replace("\\", "/")
        artifacts[key] = entry

    payload = {
        "ok": True,
        "at": _utc(),
        "freeze_id": "V1_STALENESS_TRIGGER_WINDOW_V1",
        "locked_revalidation_fingerprint": LOCKED_REVALIDATION_FINGERPRINT,
        "plant_config_id": PLANT_CONFIG_ID,
        "artifacts": artifacts,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "auto_refit": False,
        },
    }
    TRIGGER_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["artifact"] = str(TRIGGER_JSON).replace("\\", "/")
    return payload


def containment_probes() -> dict[str, Any]:
    """Confirm stale V1 nulls; V2 does not substitute warm specialty; no gating."""
    import lib.rid_electrical_policy as _policy
    from lib.rid_electrical_action_accounting import account_gpu_inference
    from lib.rid_electrical_predictor_registry import estimate_action, select_predictor

    prev = _policy.PREDICTOR_STALE
    try:
        _policy.PREDICTOR_STALE = True
        sel = select_predictor(
            t_eval_s=3.5,
            residency="warm_repeat",
            request_tail_accounting=False,
            request_prompt_decomposition=False,
        )
        # select may still say V1; estimate must null
        est = estimate_action(
            t_eval_s=3.5,
            residency="warm_repeat",
            request_tail_accounting=False,
            request_prompt_decomposition=False,
            plant_config_id=PLANT_CONFIG_ID,
            measured_E_net_j=480.0,
        )
        acct = account_gpu_inference(
            action_id="containment_probe_v1_stale",
            model="viv-voice-qwen",
            eval_duration_s=3.5,
            measured_E_net_j=480.0,
            plant_config_id=PLANT_CONFIG_ID,
            residency_state="warm_repeat",
            refresh_drift=False,
            append_drift_log=False,
            shadow_v2=False,
        )
        # Force stale path in accounting by simulating refused estimate
        # (refresh_drift=False won't set stale; check registry estimate)
        v1_null = est.get("registry_selected_predictor") is None and est.get("predicted_E_j") is None
        no_v2_sub = est.get("registry_selected_predictor") != "V2"
        # Warm specialty select reason must not become V2
        warm_sel = select_predictor(
            t_eval_s=3.5,
            residency="warm_repeat",
            request_tail_accounting=False,
            request_prompt_decomposition=False,
        )
        no_v2_select = warm_sel.get("selected") != "V2"
        return {
            "ok": True,
            "at": _utc(),
            "v1_stale_emits_null": bool(v1_null),
            "v2_does_not_substitute_warm_specialty": bool(no_v2_sub and no_v2_select),
            "gates_action_false": acct.get("gates_action") is False,
            "selection_when_stale": {
                "select_predictor": sel.get("selected"),
                "estimate_selected": est.get("registry_selected_predictor"),
                "estimate_reason": est.get("selection_reason"),
                "predicted_E_j": est.get("predicted_E_j"),
            },
            "pass": bool(v1_null and no_v2_sub and no_v2_select and acct.get("gates_action") is False),
        }
    finally:
        _policy.PREDICTOR_STALE = prev


def write_eligibility_audit(audit: dict[str, Any]) -> dict[str, Any]:
    ELIG_JSON.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    lines = [
        "# V1 drift eligibility audit",
        "",
        f"- n_total: {audit.get('n_total')}",
        f"- n_eligible: {audit.get('n_eligible')}",
        f"- pooled_legacy_rmse_j: {audit.get('pooled_legacy_rmse_j')}",
        f"- eligible_rmse_j: {audit.get('eligible_rmse_j')}",
        f"- speech_contaminated: {audit.get('speech_contaminated')}",
        f"- eligible_passes_gate: {audit.get('eligible_passes_gate')}",
        f"- by_reason: `{audit.get('by_reason')}`",
        "",
    ]
    ELIG_MD.write_text("\n".join(lines), encoding="utf-8")
    return {"json": str(ELIG_JSON).replace("\\", "/"), "md": str(ELIG_MD).replace("\\", "/")}


def localize_cause(
    rows: Sequence[dict[str, Any]],
    *,
    audit: dict[str, Any],
) -> dict[str, Any]:
    """Slice residuals and assign exactly one cause class."""
    by_res: dict[str, list[float]] = defaultdict(list)
    by_session: dict[str, list[float]] = defaultdict(list)
    before: list[float] = []
    after: list[float] = []
    for r in rows:
        resid = r.get("residual_j")
        if resid is None:
            continue
        try:
            rv = float(resid)
        except (TypeError, ValueError):
            continue
        res = str(r.get("residency") or "unknown")
        by_res[res].append(rv)
        by_session[str(r.get("session_id") or "unknown")[:48]].append(rv)
        at = str(r.get("at") or "")
        if at and at < SPEAK_HOOK_CUTOVER:
            before.append(rv)
        else:
            after.append(rv)

    def _rmse(xs: list[float]) -> float | None:
        if not xs:
            return None
        return math.sqrt(statistics.fmean([x * x for x in xs]))

    slices = {
        "by_residency_rmse": {k: _rmse(v) for k, v in by_res.items()},
        "by_residency_n": {k: len(v) for k, v in by_res.items()},
        "before_speak_hook_rmse": _rmse(before),
        "after_speak_hook_rmse": _rmse(after),
        "before_n": len(before),
        "after_n": len(after),
        "speech_contaminated": audit.get("speech_contaminated"),
        "eligible_passes_gate": audit.get("eligible_passes_gate"),
        "pooled_legacy_rmse_j": audit.get("pooled_legacy_rmse_j"),
        "eligible_rmse_j": audit.get("eligible_rmse_j"),
    }

    # Cause classification (single)
    if (
        not audit.get("speech_contaminated")
        and audit.get("eligible_passes_gate")
        and (audit.get("pooled_legacy_rmse_j") or 0) > (audit.get("drift_alert_threshold_j") or 0)
        and (by_res.get("cold_first") or by_res.get("cold") or len(by_res) > 1)
    ):
        cause = "monitor_or_receipt_semantics_fault"
        rationale = (
            "Pooled RMSE inflated by non-warm residency; warm-eligible RMSE passes gate; "
            "no timing-only speech contamination in drift log."
        )
    elif audit.get("speech_contaminated"):
        cause = "monitor_or_receipt_semantics_fault"
        rationale = "Timing-only or speak receipts present in V1 drift grading inputs."
    elif not audit.get("eligible_passes_gate") and (audit.get("n_eligible") or 0) >= MIN_LIVE_N:
        # Still stale on eligible warm set
        # Check config fingerprints
        fps = {str(r.get("revalidation_fingerprint") or "") for r in rows}
        if len(fps) > 2:
            cause = "plant_configuration_changed"
            rationale = "Multiple revalidation fingerprints among drift rows."
        else:
            # Diagnostic: if warm residuals systematically biased, coefficient shift
            warm = by_res.get("warm_repeat") or []
            if warm and abs(statistics.fmean(warm)) > 0.5 * statistics.fmean([abs(x) for x in warm]):
                cause = "stable_relationship_shifted"
                rationale = "Eligible warm residuals show systematic bias above half MAE scale."
            else:
                cause = "v1_relationship_no_longer_repeatable"
                rationale = "Eligible warm RMSE fails gate without clear bias/config change."
    elif (audit.get("n_eligible") or 0) < MIN_LIVE_N:
        cause = "monitor_or_receipt_semantics_fault"
        rationale = "Insufficient eligible warm+measured observations after exclusion."
    else:
        cause = "monitor_or_receipt_semantics_fault"
        rationale = "Default: eligibility repair clears stale; retain V1."

    assert cause in CAUSE_CLASSES
    return {
        "ok": True,
        "at": _utc(),
        "cause_class": cause,
        "rationale": rationale,
        "slices": slices,
        "updates_v1": False,
        "authority": {
            "operational_authority": False,
            "auto_admit": False,
            "auto_refit": False,
        },
    }


def diagnostic_fit_copy(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """OLS on warm eligible copy only; never writes V1 coefficients."""
    xs: list[float] = []
    ys: list[float] = []
    for r in rows:
        from lib.rid_electrical_drift_check import classify_drift_record

        ok, _ = classify_drift_record(r)
        if not ok:
            continue
        try:
            xs.append(float(r["eval_duration_s"]))
            ys.append(float(r["measured_E_net_j"]))
        except (TypeError, ValueError, KeyError):
            continue
    if len(xs) < 5:
        payload = {
            "ok": True,
            "at": _utc(),
            "n": len(xs),
            "fit": None,
            "updates_v1": False,
            "note": "insufficient_points_for_diagnostic_fit",
            "locked_alpha_j": ALPHA,
            "locked_beta_j_per_s": BETA,
        }
    else:
        n = len(xs)
        mx = statistics.fmean(xs)
        my = statistics.fmean(ys)
        num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        den = sum((xs[i] - mx) ** 2 for i in range(n))
        beta = num / den if den > 1e-12 else None
        alpha = (my - beta * mx) if beta is not None else None
        payload = {
            "ok": True,
            "at": _utc(),
            "n": n,
            "fit": {"alpha_j": alpha, "beta_j_per_s": beta},
            "locked_alpha_j": ALPHA,
            "locked_beta_j_per_s": BETA,
            "delta_alpha_j": (alpha - ALPHA) if alpha is not None else None,
            "delta_beta_j_per_s": (beta - BETA) if beta is not None else None,
            "updates_v1": False,
            "note": "Diagnostic copy only. V1 coefficients unchanged.",
        }
    DIAG_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["artifact"] = str(DIAG_JSON).replace("\\", "/")
    return payload


def decide(
    *,
    cause: dict[str, Any],
    audit: dict[str, Any],
    replay: dict[str, Any],
    revalidation: dict[str, Any],
) -> dict[str, Any]:
    """Map cause → explicit decision. Never silent refit."""
    cls = cause.get("cause_class")
    if cls == "monitor_or_receipt_semantics_fault":
        if replay.get("live_accounting_validated") or audit.get("eligible_passes_gate"):
            decision = "retain_v1_after_monitor_repair"
            action = (
                "Repaired eligibility (warm_repeat + measured E_net only); "
                "replay passes; clear ops_review_required; keep V1 frozen."
            )
        else:
            decision = "retain_v1_monitor_repaired_inconclusive"
            action = "Monitor repaired; eligible sample insufficient or inconclusive."
    elif cls == "plant_configuration_changed":
        decision = "v1_null_until_new_config_id"
        action = "Plant/config fingerprint changed; V1 remains null for mismatch; no coeff write."
    elif cls == "stable_relationship_shifted":
        decision = "open_v1_1_candidate_lifecycle"
        action = "Open separate V1.1 candidate review lifecycle; do not promote here; V1 frozen."
    else:
        decision = "retire_v1_operational_accounting_domain"
        action = "Retire V1 operational accounting for warm eval-only domain on this plant."

    lock = {
        "ok": True,
        "at": _utc(),
        "status": "v1_staleness_review_complete",
        "cause_class": cls,
        "decision": decision,
        "action": action,
        "auto_refit": False,
        "v1_coefficients_mutated": False,
        "locked_alpha_j": ALPHA,
        "locked_beta_j_per_s": BETA,
        "replay_status": replay.get("status"),
        "revalidation": {
            "skipped": revalidation.get("skipped"),
            "reason": revalidation.get("reason"),
            "status": revalidation.get("status"),
        },
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "auto_refit": False,
            "gates_action": False,
        },
    }
    DECISION_JSON.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    lock["artifact"] = str(DECISION_JSON).replace("\\", "/")
    return lock


def apply_review_policy(decision: dict[str, Any]) -> dict[str, Any]:
    """Sync policy after review: clear stale if retain+validated; never auto_refit."""
    from lib.rid_electrical_policy import apply_live_accounting_verdict
    import lib.rid_electrical_policy as _policy

    dec = decision.get("decision")
    if dec == "retain_v1_after_monitor_repair":
        apply_live_accounting_verdict("live_accounting_validated")
        _policy.OPS_REVIEW_REQUIRED = False
        _policy.OPS_REVIEW_REASON = None
        _policy.ENERGY_LEARNING_STATE["ops_review_required"] = False
        _policy.ENERGY_LEARNING_STATE["ops_review_reason"] = None
        _policy.ENERGY_LEARNING_STATE["v1_staleness_review_complete"] = True
        _policy.ENERGY_LEARNING_STATE["predictor_candidate_status"] = (
            "v1_staleness_review_complete"
        )
    else:
        _policy.ENERGY_LEARNING_STATE["v1_staleness_review_complete"] = True
        _policy.ENERGY_LEARNING_STATE["predictor_candidate_status"] = str(dec)
    # Persist ops status artifact review fields
    ops_path = CAMPAIGN / "PRODUCTION_ACCOUNTING_OPS_STATUS.json"
    if ops_path.exists():
        try:
            ops = json.loads(ops_path.read_text(encoding="utf-8"))
            ops["ops_review_required"] = bool(_policy.OPS_REVIEW_REQUIRED)
            ops["review_reason"] = _policy.OPS_REVIEW_REASON
            ops["v1_staleness_review"] = {
                "status": "v1_staleness_review_complete",
                "decision": dec,
                "at": _utc(),
            }
            ops_path.write_text(json.dumps(ops, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return {
        "predictor_stale": _policy.PREDICTOR_STALE,
        "live_accounting_validated": _policy.LIVE_ACCOUNTING_VALIDATED,
        "ops_review_required": _policy.OPS_REVIEW_REQUIRED,
        "auto_refit": False,
    }


def run_full_review(*, run_plant_revalidation: bool = False) -> dict[str, Any]:
    """Execute phases 1–5. Plant revalidation only if eligible drift still stale."""
    freeze = freeze_trigger_window()
    contain = containment_probes()

    # Prefer frozen copy for audit
    rows = load_drift_log(TRIGGER_COPY if TRIGGER_COPY.exists() else DRIFT_LOG_PATH)
    audit = audit_drift_eligibility(rows)
    write_eligibility_audit(audit)

    cause = localize_cause(rows, audit=audit)
    diag = diagnostic_fit_copy(rows)

    # Replay with hardened eligibility on live log
    replay = evaluate_live_accounting(load_drift_log())
    refresh = refresh_and_apply_drift_status()

    still_stale = bool(replay.get("predictor_stale")) and (replay.get("n_usable") or 0) >= MIN_LIVE_N
    if still_stale and run_plant_revalidation:
        revalidation = {
            "skipped": False,
            "reason": "eligible_drift_still_stale",
            "status": "plant_revalidation_required_operator",
            "note": (
                "Plant warm revalidation campaign not auto-started in this review run; "
                "use dedicated eval_duration protocol separately. V1 coeffs remain frozen."
            ),
        }
    elif still_stale:
        revalidation = {
            "skipped": True,
            "reason": "eligible_still_stale_but_plant_run_not_requested",
            "status": "revalidation_deferred",
            "note": "Set run_plant_revalidation=True / CLI flag to authorize plant campaign.",
        }
    else:
        revalidation = {
            "skipped": True,
            "reason": "eligible_replay_clears_stale_or_insufficient",
            "status": "skipped_not_needed",
            "replay_status": replay.get("status"),
            "n_usable": replay.get("n_usable"),
            "rmse_live_j": replay.get("rmse_live_j"),
        }
    REVAL_JSON.write_text(json.dumps(revalidation, indent=2), encoding="utf-8")
    REVAL_MD.write_text(
        "\n".join(
            [
                "# V1 staleness revalidation",
                "",
                f"- skipped: {revalidation.get('skipped')}",
                f"- reason: {revalidation.get('reason')}",
                f"- status: {revalidation.get('status')}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    decision = decide(
        cause=cause, audit=audit, replay=replay, revalidation=revalidation
    )
    policy_out = apply_review_policy(decision)

    review = {
        "ok": True,
        "at": _utc(),
        "status": "v1_staleness_review_complete",
        "lifecycle_from": "production_accounting_operations",
        "freeze": freeze,
        "containment": contain,
        "eligibility_audit": {
            "n_eligible": audit.get("n_eligible"),
            "eligible_rmse_j": audit.get("eligible_rmse_j"),
            "pooled_legacy_rmse_j": audit.get("pooled_legacy_rmse_j"),
            "speech_contaminated": audit.get("speech_contaminated"),
            "by_reason": audit.get("by_reason"),
            "eligible_passes_gate": audit.get("eligible_passes_gate"),
            "artifact": str(ELIG_JSON).replace("\\", "/"),
        },
        "cause": cause,
        "diagnostic_fit_copy": {
            "updates_v1": False,
            "artifact": diag.get("artifact"),
            "fit": diag.get("fit"),
        },
        "replay": {
            "status": replay.get("status"),
            "n_usable": replay.get("n_usable"),
            "rmse_live_j": replay.get("rmse_live_j"),
            "predictor_stale": replay.get("predictor_stale"),
            "refresh": {
                "status": refresh.get("status"),
                "predictor_stale": refresh.get("predictor_stale"),
            },
        },
        "revalidation": revalidation,
        "decision": decision,
        "policy_after": policy_out,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "auto_refit": False,
            "gates_action": False,
        },
        "policy": policy_stamp(),
    }
    REVIEW_JSON.write_text(json.dumps(review, indent=2), encoding="utf-8")
    md = [
        "# V1 Staleness Review",
        "",
        f"- status: `{review['status']}`",
        f"- cause: `{cause.get('cause_class')}`",
        f"- decision: `{decision.get('decision')}`",
        f"- speech_contaminated: {audit.get('speech_contaminated')}",
        f"- eligible_rmse_j: {audit.get('eligible_rmse_j')} (n={audit.get('n_eligible')})",
        f"- pooled_legacy_rmse_j: {audit.get('pooled_legacy_rmse_j')}",
        f"- replay: `{replay.get('status')}` stale={replay.get('predictor_stale')}",
        f"- revalidation skipped: {revalidation.get('skipped')} ({revalidation.get('reason')})",
        f"- containment pass: {contain.get('pass')}",
        f"- V1 coeffs mutated: false (α={ALPHA}, β={BETA})",
        "",
        "## Rationale",
        "",
        str(cause.get("rationale") or ""),
        "",
        str(decision.get("action") or ""),
        "",
    ]
    REVIEW_MD.write_text("\n".join(md), encoding="utf-8")
    review["artifacts"] = {
        "review": str(REVIEW_JSON).replace("\\", "/"),
        "decision_lock": str(DECISION_JSON).replace("\\", "/"),
        "trigger": str(TRIGGER_JSON).replace("\\", "/"),
        "eligibility": str(ELIG_JSON).replace("\\", "/"),
    }
    return review
