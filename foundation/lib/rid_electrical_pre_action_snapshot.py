#!/usr/bin/env python3
"""Immutable PreActionSnapshotV2 capture contract for dual pre-action energy.

Leakage-free: features must exist before execution. Never gates actions.
planned_response_profile is immutable metadata for net-domain admission only —
never a fitted feature.
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_predictor import (
    ALPHA,
    BETA,
    DOMAIN_MAX_S,
    DOMAIN_MIN_S,
    PLANT_CONFIG_ID,
)

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
SNAPSHOT_DIR = CAMPAIGN / "pre_action_snapshots"
CORPUS_JSONL = CAMPAIGN / "pre_action_corpus_rows.jsonl"

MODEL_ID = "viv-voice-qwen"
QUANTIZATION = "Q6_K"
EXECUTOR = "ollama_generate"
SCHEMA_VERSION = "PreActionSnapshotV2"
SCHEMA_VERSION_V1 = "PreActionSnapshotV1"

PLANNED_RESPONSE_PROFILES = frozenset({"short", "measurable", "unknown"})
PROFILE_SHORT = "short"
PROFILE_MEASURABLE = "measurable"
PROFILE_UNKNOWN = "unknown"

MIN_INTEGRATION_SAMPLES = 3
SNR_NET_MIN = 3.0

REQUIRED_FEATURE_KEYS = (
    "num_predict",
    "prompt_utf8_bytes",
    "prompt_word_count",
    "prompt_message_count",
    "gpu_temp_start_c",
    "settled_idle_power_w",
    "trailing_throughput_tps",
    "throughput_history_count",
)

FORBIDDEN_FEATURE_KEYS = frozenset(
    {
        "eval_duration_s",
        "prompt_eval_duration_s",
        "actual_eval_tokens",
        "actual_generated_tokens",
        "measured_E_net_j",
        "E_net_raw_j",
        "E_net_j",
        "E_generate_j",
        "E_action_j",
        "residual_j",
        "gpu_temp_end_c",
        "completion_temp_c",
        "prompt_eval_count",  # post-action; never copy into pre-action features
        "eval_count",
        "prompt_eval_duration_ns",
        "eval_duration_ns",
        "integration_wall_ratio",
        "n_samples",
        "sample_count",
        "SNR_net",
        "snr_net",
        "done_reason",  # post-action oracle only; never deployable
        "planned_response_profile",  # admission metadata, not a fitted feature
    }
)

AUTHORITY_FALSE = {
    "operational_authority": False,
    "master_routing_authorized": False,
    "gates_action": False,
    "auto_admit": False,
    "auto_refit": False,
    "learning_admission_granted": False,
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _day_id(ts: str | None = None) -> str:
    raw = ts or _utc()
    return raw[:10]


def model_config_hash(
    *,
    model: str = MODEL_ID,
    quantization: str = QUANTIZATION,
    executor: str = EXECUTOR,
    plant_config_id: str = PLANT_CONFIG_ID,
) -> str:
    payload = {
        "model": model,
        "quantization": quantization,
        "executor": executor,
        "plant_config_id": plant_config_id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


LOCKED_MODEL_CONFIG_HASH = model_config_hash()


def profile_from_prompt_variant(prompt_variant: str | None) -> str:
    """Map predeclared prompt variant to immutable planned_response_profile."""
    pv = str(prompt_variant or "").strip().lower()
    if pv == "short":
        return PROFILE_SHORT
    if pv in {"medium", "long"}:
        return PROFILE_MEASURABLE
    return PROFILE_UNKNOWN


def prompt_stats(prompt: str) -> dict[str, int]:
    text = str(prompt or "")
    return {
        "prompt_utf8_bytes": len(text.encode("utf-8")),
        "prompt_word_count": len(text.split()),
        "prompt_message_count": 1,
    }


def canonical_snapshot_body(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Fields included in the immutable hash (excludes snapshot_hash itself)."""
    keys = [
        "schema_version",
        "snapshot_id",
        "action_id",
        "at",
        "collection_session_id",
        "day_id",
        "plant_config_id",
        "model",
        "quantization",
        "executor",
        "model_config_hash",
        "residency",
        "num_predict",
        "prompt_utf8_bytes",
        "prompt_word_count",
        "prompt_message_count",
        "gpu_temp_start_c",
        "settled_idle_power_w",
        "trailing_throughput_tps",
        "throughput_history_count",
        "coolant_temp_c",
        "prompt_token_count_pre",
        "prompt_variant",
        "planned_response_profile",
        "collection_group",
        "block_kind",
        "fail_soft",
        "action_contract_hash",
    ]
    return {k: snapshot.get(k) for k in keys}


def compute_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    body = canonical_snapshot_body(snapshot)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def capture_pre_action_snapshot(
    *,
    action_id: str,
    num_predict: int,
    prompt: str,
    gpu_temp_start_c: float,
    settled_idle_power_w: float,
    trailing_throughput_tps: float | None,
    throughput_history_count: int,
    collection_session_id: str,
    collection_group: int | None = None,
    prompt_variant: str | None = None,
    planned_response_profile: str | None = None,
    block_kind: str | None = None,
    plant_config_id: str = PLANT_CONFIG_ID,
    model: str = MODEL_ID,
    quantization: str = QUANTIZATION,
    executor: str = EXECUTOR,
    residency: str = "warm_repeat",
    coolant_temp_c: float | None = None,
    prompt_token_count_pre: int | None = None,
    fail_soft: bool = False,
    persist: bool = True,
    at: str | None = None,
    schema_version: str = SCHEMA_VERSION,
    action_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture an immutable pre-action snapshot after settle, before inference."""
    ts = at or _utc()
    stats = prompt_stats(prompt)
    profile = str(planned_response_profile or profile_from_prompt_variant(prompt_variant))
    if profile not in PLANNED_RESPONSE_PROFILES:
        profile = PROFILE_UNKNOWN
    contract_hash = None
    contract_obj = None
    if action_contract is not None:
        from lib.rid_electrical_pre_action_action_contract import (
            verify_action_contract_integrity,
        )

        contract_obj = dict(action_contract)
        ok_c, reason_c = verify_action_contract_integrity(contract_obj)
        if not ok_c:
            raise ValueError(f"action_contract_integrity:{reason_c}")
        contract_hash = str(contract_obj.get("contract_hash"))
    snap: dict[str, Any] = {
        "schema_version": str(schema_version),
        "snapshot_id": str(uuid.uuid4()),
        "action_id": str(action_id),
        "at": ts,
        "collection_session_id": str(collection_session_id),
        "day_id": _day_id(ts),
        "plant_config_id": str(plant_config_id),
        "model": str(model),
        "quantization": str(quantization),
        "executor": str(executor),
        "model_config_hash": model_config_hash(
            model=model,
            quantization=quantization,
            executor=executor,
            plant_config_id=plant_config_id,
        ),
        "residency": str(residency),
        "num_predict": int(num_predict),
        "prompt_utf8_bytes": stats["prompt_utf8_bytes"],
        "prompt_word_count": stats["prompt_word_count"],
        "prompt_message_count": stats["prompt_message_count"],
        "gpu_temp_start_c": float(gpu_temp_start_c),
        "settled_idle_power_w": float(settled_idle_power_w),
        "trailing_throughput_tps": (
            float(trailing_throughput_tps)
            if trailing_throughput_tps is not None
            else None
        ),
        "throughput_history_count": int(throughput_history_count),
        "coolant_temp_c": (
            float(coolant_temp_c) if coolant_temp_c is not None else None
        ),
        "prompt_token_count_pre": (
            int(prompt_token_count_pre) if prompt_token_count_pre is not None else None
        ),
        "prompt_variant": prompt_variant,
        "planned_response_profile": profile,
        "collection_group": collection_group,
        "block_kind": block_kind or "primary",
        "fail_soft": bool(fail_soft),
        "action_contract_hash": contract_hash,
        **AUTHORITY_FALSE,
        "learning_admission_withheld": True,
    }
    if contract_obj is not None:
        # Full contract stored alongside snapshot; hash is in immutable body.
        snap["action_contract"] = contract_obj
    snap["snapshot_hash"] = compute_snapshot_hash(snap)
    if persist:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SNAPSHOT_DIR / f"{snap['snapshot_id']}.json"
        path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        snap["artifact"] = str(path).replace("\\", "/")
    return snap


def verify_snapshot_integrity(snapshot: Mapping[str, Any]) -> tuple[bool, str]:
    expected = compute_snapshot_hash(snapshot)
    got = str(snapshot.get("snapshot_hash") or "")
    if not got:
        return False, "missing_snapshot_hash"
    if got != expected:
        return False, "snapshot_hash_mismatch"
    return True, "ok"


def required_features_present(snapshot: Mapping[str, Any]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for k in REQUIRED_FEATURE_KEYS:
        v = snapshot.get(k)
        if v is None:
            missing.append(k)
            continue
        if k == "trailing_throughput_tps" and (
            not isinstance(v, (int, float)) or not math.isfinite(float(v)) or float(v) <= 0
        ):
            missing.append(k)
    return (len(missing) == 0), missing


def extract_feature_vector(snapshot: Mapping[str, Any]) -> dict[str, float] | None:
    """Numeric feature matrix for training (coolant excluded from v1 matrix)."""
    ok, missing = required_features_present(snapshot)
    if not ok:
        return None
    if str(snapshot.get("residency") or "") != "warm_repeat":
        return None
    if str(snapshot.get("model_config_hash") or "") != LOCKED_MODEL_CONFIG_HASH:
        return None
    if str(snapshot.get("plant_config_id") or "") != PLANT_CONFIG_ID:
        return None
    return {
        "num_predict": float(snapshot["num_predict"]),
        "prompt_utf8_bytes": float(snapshot["prompt_utf8_bytes"]),
        "prompt_word_count": float(snapshot["prompt_word_count"]),
        "prompt_message_count": float(snapshot["prompt_message_count"]),
        "gpu_temp_start_c": float(snapshot["gpu_temp_start_c"]),
        "settled_idle_power_w": float(snapshot["settled_idle_power_w"]),
        "trailing_throughput_tps": float(snapshot["trailing_throughput_tps"]),
        "throughput_history_count": float(snapshot["throughput_history_count"]),
    }


def feature_leakage_audit(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Detect forbidden post-action fields in feature payloads."""
    leaks: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        feats = row.get("features") if isinstance(row.get("features"), dict) else None
        snap = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else row
        sources = []
        if feats is not None:
            sources.append(("features", feats))
        if isinstance(snap, Mapping):
            # Only flag if forbidden keys appear as claimed pre-action features
            pre_keys = set(REQUIRED_FEATURE_KEYS) | set(feats.keys() if feats else [])
            for fk in FORBIDDEN_FEATURE_KEYS:
                if fk in (feats or {}) or (
                    fk in snap
                    and fk
                    in {
                        "eval_duration_s",
                        "measured_E_net_j",
                        "prompt_eval_count",
                        "actual_eval_tokens",
                    }
                    and row.get("use_post_action_as_feature")
                ):
                    leaks.append(
                        {
                            "index": i,
                            "field": fk,
                            "snapshot_id": (snap or {}).get("snapshot_id"),
                        }
                    )
            # Hard rule: prompt_eval_count must never appear in features
            if feats and "prompt_eval_count" in feats:
                leaks.append(
                    {
                        "index": i,
                        "field": "prompt_eval_count",
                        "snapshot_id": snap.get("snapshot_id"),
                    }
                )
            _ = pre_keys  # retained for clarity
            _ = sources
        if feats:
            for fk in FORBIDDEN_FEATURE_KEYS:
                if fk in feats:
                    leaks.append(
                        {
                            "index": i,
                            "field": fk,
                            "snapshot_id": (snap or {}).get("snapshot_id")
                            if isinstance(snap, Mapping)
                            else None,
                        }
                    )
    # Deduplicate
    seen = set()
    uniq = []
    for L in leaks:
        key = (L.get("index"), L.get("field"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(L)
    return {
        "ok": len(uniq) == 0,
        "n_rows": len(rows),
        "n_leaks": len(uniq),
        "leaks": uniq,
        "forbidden_keys": sorted(FORBIDDEN_FEATURE_KEYS),
    }


def join_pre_action_outcome(
    snapshot_id: str,
    measured_outcome: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Join immutable snapshot with measured outcome into a dual-label corpus row."""
    snap: Mapping[str, Any] | None = snapshot
    if snap is None:
        path = SNAPSHOT_DIR / f"{snapshot_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"snapshot not found: {snapshot_id}")
        snap = json.loads(path.read_text(encoding="utf-8"))
    ok_hash, hash_reason = verify_snapshot_integrity(snap)
    if not ok_hash:
        raise ValueError(f"snapshot integrity failed: {hash_reason}")

    outcome_at = str(measured_outcome.get("at") or _utc())
    snap_at = str(snap.get("at") or "")
    if snap_at and outcome_at < snap_at:
        raise ValueError("feature/label timestamp inversion")

    measurement_state = str(measured_outcome.get("measurement_state") or "measured")
    e_net = measured_outcome.get("E_net_raw_j")
    if e_net is None:
        e_net = measured_outcome.get("measured_E_net_j")
    e_gen = measured_outcome.get("E_generate_j")
    if e_gen is None:
        e_gen = measured_outcome.get("E_action_immediate_j")

    features = extract_feature_vector(snap)
    eligible_gross, reasons_gross = gross_label_eligibility(snap, measured_outcome, features)
    eligible_net, reasons_net = net_label_eligibility(snap, measured_outcome, features)
    # Legacy single-target eligible == net (V1 behavior for net-only consumers)
    eligible = eligible_net
    reasons = list(reasons_net)

    profile = str(snap.get("planned_response_profile") or PROFILE_UNKNOWN)
    n_samples = measured_outcome.get("n_samples")
    if n_samples is None:
        n_samples = measured_outcome.get("sample_count")
    row = {
        "schema_version": "PreActionCorpusRowV2",
        "snapshot_id": snap["snapshot_id"],
        "action_id": snap.get("action_id"),
        "collection_session_id": snap.get("collection_session_id"),
        "day_id": snap.get("day_id"),
        "collection_group": snap.get("collection_group"),
        "block_kind": snap.get("block_kind") or "primary",
        "planned_response_profile": profile,
        "snapshot": dict(snap),
        "features": features,
        "label": {
            "y_gross": "E_generate",
            "y_net": "E_net_raw",
            "y": "E_net_raw",
            "E_generate_j": float(e_gen) if e_gen is not None else None,
            "E_net_raw_j": float(e_net) if e_net is not None else None,
            "measurement_state": measurement_state,
            "snr_net": measured_outcome.get("SNR_net")
            or measured_outcome.get("snr_net"),
            "settle_ok": measured_outcome.get("settle_ok"),
            "integration_ok": measured_outcome.get("integration_ok"),
            "integration_wall_ratio": measured_outcome.get("integration_wall_ratio"),
            "n_samples": n_samples,
            "actual_eval_tokens": measured_outcome.get("actual_eval_tokens")
            or measured_outcome.get("eval_count"),
            "actual_generated_tokens": measured_outcome.get("actual_generated_tokens"),
            "eval_duration_s": measured_outcome.get("eval_duration_s"),
            "prompt_eval_duration_s": measured_outcome.get("prompt_eval_duration_s"),
            "outcome_at": outcome_at,
            "eligible_gross": eligible_gross,
            "eligible_net": eligible_net,
            "gross_eligibility_reasons": reasons_gross,
            "net_eligibility_reasons": reasons_net,
        },
        "eligible_gross": eligible_gross,
        "eligible_net": eligible_net,
        "gross_eligibility_reasons": reasons_gross,
        "net_eligibility_reasons": reasons_net,
        "eligible": eligible,
        "eligibility_reasons": reasons,
        "confidence": measured_outcome.get("confidence")
        or ("ok" if eligible_gross or eligible_net else "ineligible"),
        **AUTHORITY_FALSE,
    }
    if persist:
        CORPUS_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with CORPUS_JSONL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return row


def _plant_structural_reasons(
    snapshot: Mapping[str, Any],
    outcome: Mapping[str, Any],
    features: dict[str, float] | None,
) -> list[str]:
    reasons: list[str] = []
    evidence = str(
        outcome.get("evidence_source")
        or snapshot.get("evidence_source")
        or ""
    )
    is_plant = evidence == "plant"
    if features is None:
        reasons.append("missing_required_features_or_config")
    ok_hash, hash_reason = verify_snapshot_integrity(snapshot)
    if not ok_hash:
        reasons.append(hash_reason)
    if str(snapshot.get("residency") or "") != "warm_repeat":
        reasons.append("non_warm_residency")
    if str(outcome.get("measurement_state") or "measured") == "timing_only":
        reasons.append("timing_only")
    if outcome.get("settle_ok") is False:
        reasons.append("settle_failed")
    if outcome.get("integration_ok") is False:
        reasons.append("integration_failed")
    if outcome.get("snapshot_hook_failed"):
        reasons.append("snapshot_hook_failed")
    if is_plant and outcome.get("snr_gate_deferred"):
        reasons.append("snr_gate_deferred_forbidden_for_plant")
    if is_plant:
        try:
            t = float(snapshot.get("gpu_temp_start_c"))
            p = float(snapshot.get("settled_idle_power_w"))
            if abs(t - 50.0) < 1e-9 and abs(p - 55.0) < 1e-9:
                if not outcome.get("settle_fields_matched"):
                    reasons.append("placeholder_settle_fields")
        except (TypeError, ValueError):
            reasons.append("invalid_settle_fields")
        settle_temp = outcome.get("settle_gpu_temp_c")
        settle_p = outcome.get("settle_P_idle_stable_w")
        try:
            if settle_temp is not None and abs(
                float(snapshot["gpu_temp_start_c"]) - float(settle_temp)
            ) > 1e-6:
                reasons.append("snapshot_temp_ne_settle")
            if settle_p is not None and abs(
                float(snapshot["settled_idle_power_w"]) - float(settle_p)
            ) > 1e-6:
                reasons.append("snapshot_idle_ne_settle")
        except (TypeError, ValueError, KeyError):
            reasons.append("settle_equality_check_failed")
        snap_at = str(snapshot.get("at") or "")
        inf_at = str(outcome.get("inference_request_at") or "")
        snap_mono = outcome.get("pre_inference_hook_mono")
        if snap_mono is None:
            snap_mono = snapshot.get("pre_inference_hook_mono")
        inf_mono = outcome.get("inference_request_mono")
        if snap_at and inf_at:
            if snap_at > inf_at:
                reasons.append("snapshot_not_before_inference")
            elif snap_at == inf_at:
                try:
                    if (
                        snap_mono is None
                        or inf_mono is None
                        or float(snap_mono) >= float(inf_mono)
                    ):
                        reasons.append("snapshot_not_before_inference")
                except (TypeError, ValueError):
                    reasons.append("snapshot_not_before_inference")
    plant = str(outcome.get("plant_config_id") or snapshot.get("plant_config_id") or "")
    if plant != PLANT_CONFIG_ID:
        reasons.append("plant_config_mismatch")
    return reasons


def gross_label_eligibility(
    snapshot: Mapping[str, Any],
    outcome: Mapping[str, Any],
    features: dict[str, float] | None,
) -> tuple[bool, list[str]]:
    """Gross head: finite positive E_generate + exact integration + samples."""
    reasons = _plant_structural_reasons(snapshot, outcome, features)
    e_gen = outcome.get("E_generate_j")
    if e_gen is None:
        e_gen = outcome.get("E_action_immediate_j")
    try:
        eg = float(e_gen) if e_gen is not None else None
    except (TypeError, ValueError):
        eg = None
        reasons.append("E_generate_invalid")
    if eg is None:
        reasons.append("missing_E_generate")
    elif not math.isfinite(eg) or eg <= 0:
        reasons.append("E_generate_not_positive_finite")
    n_samples = outcome.get("n_samples")
    if n_samples is None:
        n_samples = outcome.get("sample_count")
    try:
        ns = int(n_samples) if n_samples is not None else None
    except (TypeError, ValueError):
        ns = None
        reasons.append("n_samples_invalid")
    if ns is None:
        # Synthetic harness may omit; accept if integration_ok explicitly True
        if outcome.get("integration_ok") is True and not str(
            outcome.get("evidence_source") or snapshot.get("evidence_source") or ""
        ) == "plant":
            pass
        elif outcome.get("integration_ok") is True and outcome.get("synthetic"):
            pass
        else:
            # Allow synthetic via deferred sample count when integration marked ok
            evidence = str(
                outcome.get("evidence_source")
                or snapshot.get("evidence_source")
                or ""
            )
            if evidence in {"", "synthetic_harness_only"} and outcome.get(
                "integration_ok"
            ) is True:
                pass
            else:
                reasons.append("n_samples_missing")
    elif ns < MIN_INTEGRATION_SAMPLES:
        reasons.append("n_samples_insufficient")
    return (len(reasons) == 0), reasons


def net_label_eligibility(
    snapshot: Mapping[str, Any],
    outcome: Mapping[str, Any],
    features: dict[str, float] | None,
) -> tuple[bool, list[str]]:
    """Net head: measurable profile + SNR>=3 + gross structural gates + E_net."""
    # Start from gross structural (without requiring E_generate positivity for net-only
    # diagnostics — still require settle/integration/hash).
    reasons = _plant_structural_reasons(snapshot, outcome, features)
    profile = str(snapshot.get("planned_response_profile") or PROFILE_UNKNOWN)
    if profile != PROFILE_MEASURABLE:
        reasons.append("profile_not_measurable_for_net")
    e_net = outcome.get("E_net_raw_j")
    if e_net is None:
        e_net = outcome.get("measured_E_net_j")
    if e_net is None:
        reasons.append("missing_E_net_raw")
    evidence = str(
        outcome.get("evidence_source")
        or snapshot.get("evidence_source")
        or ""
    )
    is_plant = evidence == "plant"
    snr = outcome.get("SNR_net")
    if snr is None:
        snr = outcome.get("snr_net")
    if snr is not None:
        try:
            if float(snr) < SNR_NET_MIN:
                reasons.append("snr_net_below_3")
        except (TypeError, ValueError):
            reasons.append("snr_net_invalid")
    else:
        if is_plant or not outcome.get("snr_gate_deferred"):
            reasons.append("snr_net_missing")
    # Short/unknown: always ineligible for net even if SNR crosses 3
    if profile in {PROFILE_SHORT, PROFILE_UNKNOWN}:
        if "profile_not_measurable_for_net" not in reasons:
            reasons.append("profile_not_measurable_for_net")
    return (len(reasons) == 0), reasons


def label_eligibility(
    snapshot: Mapping[str, Any],
    outcome: Mapping[str, Any],
    features: dict[str, float] | None,
) -> tuple[bool, list[str]]:
    """Backward-compatible: net eligibility (dual net head)."""
    return net_label_eligibility(snapshot, outcome, features)


def predict_pre_action_energy(
    snapshot: Mapping[str, Any],
    *,
    gross_candidate: Mapping[str, Any] | None = None,
    net_candidate: Mapping[str, Any] | None = None,
    plant_config_id: str | None = None,
    model_config_hash_value: str | None = None,
) -> dict[str, Any]:
    """Dual prediction interface. Never gates. Profile routes net domain only."""
    profile = str(snapshot.get("planned_response_profile") or PROFILE_UNKNOWN)
    feats = extract_feature_vector(snapshot) or {
        "num_predict": snapshot.get("num_predict"),
        "trailing_throughput_tps": snapshot.get("trailing_throughput_tps"),
        "throughput_history_count": snapshot.get("throughput_history_count"),
        "prompt_utf8_bytes": snapshot.get("prompt_utf8_bytes"),
        "prompt_word_count": snapshot.get("prompt_word_count"),
        "prompt_message_count": snapshot.get("prompt_message_count"),
        "gpu_temp_start_c": snapshot.get("gpu_temp_start_c"),
        "settled_idle_power_w": snapshot.get("settled_idle_power_w"),
        "model_config_hash": snapshot.get("model_config_hash"),
    }
    mch = model_config_hash_value or snapshot.get("model_config_hash")
    cfg = plant_config_id or str(snapshot.get("plant_config_id") or PLANT_CONFIG_ID)

    gross = _predict_head(
        feats,
        head="gross",
        plant_config_id=cfg,
        model_config_hash_value=str(mch) if mch is not None else None,
        candidate=gross_candidate,
        allow_baseline=True,
    )
    net: dict[str, Any]
    if profile in {PROFILE_SHORT, PROFILE_UNKNOWN}:
        net = {
            "predicted_E_net_j": None,
            "confidence": "profile_net_null",
            "in_domain": False,
            "model_id": "pre_action_energy_dual_net",
            "plant_config_id": cfg,
            "planned_response_profile": profile,
            **AUTHORITY_FALSE,
            "learning_admission_withheld": True,
        }
    else:
        net = _predict_head(
            feats,
            head="net",
            plant_config_id=cfg,
            model_config_hash_value=str(mch) if mch is not None else None,
            candidate=net_candidate,
            allow_baseline=True,
        )
        net["planned_response_profile"] = profile

    return {
        "gross": {
            "predicted_E_generate_j": gross.get("predicted_E_generate_j"),
            "confidence": gross.get("confidence"),
            "in_domain": gross.get("in_domain"),
            "source": gross.get("source"),
            "t_eval_hat_s": gross.get("t_eval_hat_s"),
        },
        "net": {
            "predicted_E_net_j": net.get("predicted_E_net_j"),
            "confidence": net.get("confidence"),
            "in_domain": net.get("in_domain"),
            "source": net.get("source"),
            "t_eval_hat_s": net.get("t_eval_hat_s"),
            "planned_response_profile": profile,
        },
        "planned_response_profile": profile,
        "plant_config_id": cfg,
        **AUTHORITY_FALSE,
        "learning_admission_withheld": True,
    }


def _predict_head(
    features: Mapping[str, Any],
    *,
    head: str,
    plant_config_id: str,
    model_config_hash_value: str | None,
    candidate: Mapping[str, Any] | None,
    allow_baseline: bool,
) -> dict[str, Any]:
    key = "predicted_E_generate_j" if head == "gross" else "predicted_E_net_j"
    out: dict[str, Any] = {
        key: None,
        "confidence": "ok",
        "in_domain": False,
        "model_id": f"pre_action_energy_dual_{head}",
        "plant_config_id": plant_config_id,
        **AUTHORITY_FALSE,
        "learning_admission_withheld": True,
    }
    if plant_config_id != PLANT_CONFIG_ID:
        out["confidence"] = "config_mismatch"
        return out
    if model_config_hash_value is not None and str(model_config_hash_value) != LOCKED_MODEL_CONFIG_HASH:
        out["confidence"] = "config_mismatch"
        return out
    try:
        num_predict = float(features["num_predict"])
        tps = float(features["trailing_throughput_tps"])
    except (KeyError, TypeError, ValueError):
        out["confidence"] = "invalid_input"
        return out
    if tps <= 0 or not math.isfinite(tps) or not math.isfinite(num_predict):
        out["confidence"] = "invalid_input"
        return out
    t_hat = num_predict / tps
    if not (DOMAIN_MIN_S <= t_hat <= DOMAIN_MAX_S):
        out["confidence"] = "out_of_validated_domain"
        out["t_eval_hat_s"] = t_hat
        return out
    if candidate is not None and candidate.get("predict_fn") is not None:
        pred = float(candidate["predict_fn"](features))
        out[key] = pred
        out["in_domain"] = True
        out["confidence"] = "candidate"
        out["t_eval_hat_s"] = t_hat
        out["source"] = str(candidate.get("model_name") or "candidate")
        return out
    if not allow_baseline:
        out["confidence"] = "no_candidate"
        return out
    # Baselines: net uses frozen V1 coeffs; gross uses same form until train fits
    # a dedicated throughput-cap baseline (train path overwrites for evaluation).
    pred = float(ALPHA) + float(BETA) * float(t_hat)
    if head == "gross":
        # Gross energy is larger than net; approximate with idle-inclusive scale
        # for null-safe routing only — training fits the real gross baseline.
        pred = float(pred) + 55.0 * float(t_hat)
        out["predicted_E_generate_j"] = pred
        out["source"] = "throughput_gross_cap_baseline"
    else:
        out["predicted_E_net_j"] = pred
        out["source"] = "throughput_v1_baseline"
    out["in_domain"] = True
    out["confidence"] = out["source"]
    out["t_eval_hat_s"] = t_hat
    return out


def predict_pre_action_E_net(
    features: Mapping[str, Any],
    *,
    plant_config_id: str | None = None,
    model_config_hash_value: str | None = None,
    candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Guarded pre-action net estimate. Never gates. Null on mismatch/invalid domain.

    Without a locked trained candidate, falls back to throughput-V1 baseline formula
    using features['num_predict'] / features['trailing_throughput_tps'].
    """
    # If features look like a full snapshot, honor profile null-routing.
    if "planned_response_profile" in features:
        dual = predict_pre_action_energy(
            features,
            net_candidate=candidate,
            plant_config_id=plant_config_id,
            model_config_hash_value=model_config_hash_value,
        )
        net = dual["net"]
        return {
            "predicted_E_net_j": net.get("predicted_E_net_j"),
            "confidence": net.get("confidence"),
            "in_domain": net.get("in_domain"),
            "model_id": "pre_action_energy_dual_net",
            "plant_config_id": plant_config_id or PLANT_CONFIG_ID,
            "t_eval_hat_s": net.get("t_eval_hat_s"),
            "source": net.get("source"),
            **AUTHORITY_FALSE,
            "learning_admission_withheld": True,
        }
    return _predict_head(
        features,
        head="net",
        plant_config_id=plant_config_id or PLANT_CONFIG_ID,
        model_config_hash_value=model_config_hash_value,
        candidate=candidate,
        allow_baseline=True,
    )


def load_snapshot(snapshot_id: str) -> dict[str, Any]:
    path = SNAPSHOT_DIR / f"{snapshot_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))
