#!/usr/bin/env python3
"""Read-only single-receipt boundary pilot for Viv/AIOS tag architecture.

Experiment: TAG_RECEIPT_BOUNDARY_PILOT_V1

Operator-approved narrow scope:
  bind one representative live item-77 receipt through LAYERED_BRIDGE and
  UNIFIED_TYPED_REGISTRY, measure operational boundary differences, and
  promote neither unless one arm shows a material operational advantage
  without semantic ambiguity or migration-risk increase.

Read-only with respect to training, checkpoints, production schemas, and
routing. Writes only timestamped reports under foundation/artifacts/auto.
"""
from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


FOUNDATION = Path(__file__).resolve().parents[1]
SCRIPTS = FOUNDATION / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import tag_architecture_ab_v1 as ab  # noqa: E402


EXPERIMENT_ID = "TAG_RECEIPT_BOUNDARY_PILOT_V1"
SCHEMA_VERSION = "tag_receipt_boundary_pilot_v1"
PRIOR_EXPERIMENT_ID = "TAG_ARCH_AB_V1"
ARM_A = ab.ARM_A
ARM_B = ab.ARM_B

DEFAULT_CENSUS = (
    FOUNDATION
    / "models"
    / "Training"
    / "current"
    / "viv_slm"
    / "model"
    / "test_training"
    / "runs"
    / "uml_speak_cheap_census"
    / "census_20260807T082414Z"
    / "census.json"
)

# Material-advantage thresholds (defined before scoring; seal-first).
MATERIAL = {
    "adapter_touch_ratio": 2.0,
    "serialized_byte_and_latency_pct": 20.0,
    "latency_cv_signal_floor": 0.25,
    "min_validation_ms_p50": 0.05,
}

PROVENANCE_KEYS = (
    "source",
    "authority",
    "survivor_hash",
    "policy_mode",
    "rid_state",
    "plant_state",
)
SEAL_KEYS = (
    "sealed_destination",
    "destination_match",
    "raw_route",
    "final_route",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime | None = None) -> str:
    return (value or _utc_now()).replace(microsecond=0).isoformat()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path).replace("\\", "/"),
        "sha256": _sha_file(path),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _load_census(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ab.ArchitectureError("census_payload_not_mapping")
    if payload.get("experiment_id") != "thesis_item_77_speak_cheap_census":
        raise ab.ArchitectureError(
            f"unexpected_census_experiment:{payload.get('experiment_id')}"
        )
    rows, supplemental = ab._extract_item77_census(payload, path)
    return dict(payload), rows, supplemental


def _row_score(row: Mapping[str, Any]) -> tuple[int, str]:
    """Higher is better for primary sealed-receipt selection."""

    score = 0
    reasons: list[str] = []
    if row.get("destination_match") is True:
        score += 20
        reasons.append("destination_match")
    sealed = row.get("sealed_destination")
    if isinstance(sealed, Mapping) and sealed.get("target_char") is not None:
        score += 5
        reasons.append("sealed_destination")
    policy = row.get("policy_mode")
    if isinstance(policy, Mapping) and policy.get("mode"):
        score += 3
        reasons.append("policy_mode")
        if str(policy.get("mode")) == "prefer_efficient_snap":
            score += 4
            reasons.append("raw_vs_final_mode")
        if str(policy.get("mode")) == "plant_rid_policy":
            score += 2
            reasons.append("plant_rid_mode")
    raw = row.get("raw_route")
    final = row.get("final_route")
    if raw is not None and final is not None:
        score += 3
        reasons.append("raw_and_final")
        if str(raw) != str(final):
            score += 6
            reasons.append("raw_ne_final")
    federation = str(row.get("federation") or "")
    if federation and federation != "INVALID":
        score += 2
        reasons.append("federation")
    domains = row.get("uml_domains")
    if isinstance(domains, list) and domains:
        score += 3
        reasons.append("uml_domains")
    for field in ("cost", "error", "cheapest", "kind"):
        if row.get(field) is not None:
            score += 1
            reasons.append(field)
    rid = row.get("rid_state")
    plant = row.get("plant_state")
    if isinstance(rid, Mapping) and rid.get("available") is True:
        score += 3
        reasons.append("rid_available")
    if isinstance(plant, Mapping) and plant.get("available") is True:
        score += 3
        reasons.append("plant_available")
    if row.get("survivor_hash"):
        score += 2
        reasons.append("survivor_hash")
    return score, ",".join(reasons)


def select_receipts(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    sealed = [dict(row) for row in rows if row.get("destination_match") is True]
    if not sealed:
        raise ab.ArchitectureError("no_sealed_destination_match_rows")
    ranked = sorted(
        sealed,
        key=lambda row: (
            _row_score(row)[0],
            1
            if str((row.get("policy_mode") or {}).get("mode") or "")
            == "prefer_efficient_snap"
            else 0,
            # Prefer stable low example ids for reproducibility when numeric.
            (
                -int(suffix)
                if (
                    str((row.get("source") or {}).get("example_id") or "").startswith(
                        "SC77-"
                    )
                    and (suffix := str((row.get("source") or {}).get("example_id") or "")
                    .rsplit("-", 1)[-1]).isdigit()
                )
                else 0
            ),
        ),
        reverse=True,
    )
    primary = ranked[0]
    primary_score, primary_reasons = _row_score(primary)
    primary_meta = {
        "role": "primary",
        "selection_score": primary_score,
        "selection_reasons": primary_reasons,
        "example_id": (primary.get("source") or {}).get("example_id"),
        "policy_mode": (primary.get("policy_mode") or {}).get("mode"),
        "destination_match": primary.get("destination_match"),
        "seal_violation_implied": primary.get("destination_match") is not True,
        "row_sha256": ab._sha_value(primary),
        "fields_bound": sorted(primary.keys()),
        "row": primary,
    }

    secondary: dict[str, Any] | None = None
    example_id = str((primary.get("source") or {}).get("example_id") or "")
    fail_candidates = [
        dict(row)
        for row in rows
        if row.get("destination_match") is False
        and str((row.get("source") or {}).get("example_id") or "") == example_id
    ]
    if fail_candidates:
        # Prefer raw_no_snap SEAL_GUARD_STOP twin of the same prompt.
        fail_candidates.sort(
            key=lambda row: (
                1 if str((row.get("policy_mode") or {}).get("mode")) == "raw_no_snap" else 0,
                _row_score({**row, "destination_match": True})[0],
            ),
            reverse=True,
        )
        fail_row = fail_candidates[0]
        secondary = {
            "role": "seal_failure_boundary_observation",
            "note": (
                "Secondary observation only; primary comparison remains the sealed "
                "receipt. Included to clarify seal-preservation behavior under "
                "SEAL_GUARD_STOP / destination_match=false."
            ),
            "example_id": (fail_row.get("source") or {}).get("example_id"),
            "policy_mode": (fail_row.get("policy_mode") or {}).get("mode"),
            "destination_match": fail_row.get("destination_match"),
            "row_sha256": ab._sha_value(fail_row),
            "fields_bound": sorted(fail_row.keys()),
            "row": fail_row,
        }
    return primary, primary_meta, secondary


def _destination_binding(row: Mapping[str, Any]) -> Any:
    sealed = row.get("sealed_destination")
    if isinstance(sealed, Mapping):
        return {
            "target_char": sealed.get("target_char"),
            "target_token_id": sealed.get("target_token_id"),
        }
    return sealed


def build_single_receipt_bundle(
    *,
    source_hashes: Mapping[str, Mapping[str, str]],
    census_path: Path,
    census_sha: str,
    row: Mapping[str, Any],
    role: str,
) -> dict[str, Any]:
    """Minimal authority+item77 bundle for one receipt (no full mouth corpus)."""

    example_id = str((row.get("source") or {}).get("example_id") or "unknown")
    mode = str((row.get("policy_mode") or {}).get("mode") or "unknown")
    bundle_id = f"receipt-boundary-{role}-{mode}-{example_id}"
    mouth = ab.build_mouth_rows()[0]
    packet = ab._build_signed_packet(0, mouth)
    authority_records, group = ab._packet_records(packet, source_hashes)
    destination = _destination_binding(row)
    item_record = ab._record(
        record_id=f"{bundle_id}:item77:0000",
        plane="item77_receipt",
        name="cheap_route_example",
        value=dict(row),
        source="item77_measurement",
        authority="measurement_only",
        confidence="measured",
        required=False,
        provenance={
            "source_path": str(census_path).replace("\\", "/"),
            "source_sha256": census_sha,
            "fixture_id": f"item77-{example_id}-{mode}",
            "state": "current",
            "observed_at": "live_census_read_only",
            "measurement_only": True,
            "established_tag": False,
            "operator_gated_if_promoted": True,
        },
        attributes={
            "established_tag": False,
            "operator_gated_if_promoted": True,
            "pilot_role": role,
            "proposed_plane_name": "item77_receipt",
            "proposed_tag_name": "cheap_route_example",
            "naming_status": "proposed_operator_gated_not_established_fact",
        },
        binding={"destination": destination},
    )
    composition = [
        {
            "binding_id": f"{bundle_id}:compose:item77",
            "record_id": item_record["record_id"],
            "plane": "item77_receipt",
            "name": "cheap_route_example",
            "destination": destination,
            "semantic_aliases": False,
        }
    ]
    return ab._normalize_bundle(
        {
            "bundle_id": bundle_id,
            "draft": "Viv renders the supplied content.",
            "records": [*authority_records, item_record],
            "packet_groups": [group],
            "composition": composition,
        }
    )


def _count_field_remaps(arm_name: str, envelope: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    """Static translation inventory for binding this one receipt."""

    if arm_name == ARM_A:
        planes = envelope["planes"]
        native_rows = planes["item77_receipt"]["rows"]
        bridge = [
            link
            for link in envelope["bridge"]
            if link.get("plane") == "item77_receipt"
        ]
        return {
            "plane_wrappers": 1,
            "native_row_shape": ["native_id", "name", "value"],
            "bridge_links_for_receipt": len(bridge),
            "field_remaps": 0,
            "value_fields_retained_natively": sorted(row.keys()),
            "adapter_touches": {
                "new_plane_namespace_slot": 1,
                "bridge_index_entries": len(bridge),
                "composition_bindings": 1,
                "typed_record_rewrites": 0,
                "packet_seal_reconstruction": False,
            },
            "native_item77_rows": len(native_rows),
            "migration_steps": [
                "retain_item77_measurement_import_v1_native_row",
                "add_bridge_link_without_value_rewrite",
                "add_composition_binding_to_sealed_destination",
            ],
            "code_fixture_touches_proxy": {
                "native_schema_rewrites": 0,
                "adapter_modules": 1,
                "fixture_records_requiring_typed_reshape": 0,
                "fixture_records_touched": 1,
            },
        }
    registry = [
        record
        for record in envelope["registry"]
        if record.get("plane") == "item77_receipt"
    ]
    return {
        "plane_wrappers": 0,
        "native_row_shape": sorted(ab.RECORD_KEYS),
        "bridge_links_for_receipt": 0,
        "field_remaps": len(ab.RECORD_KEYS),
        "value_fields_retained_natively": sorted(row.keys()),
        "adapter_touches": {
            "new_plane_namespace_slot": 0,
            "bridge_index_entries": 0,
            "composition_bindings": 1,
            "typed_record_rewrites": 1,
            "packet_seal_reconstruction": True,
        },
        "native_item77_rows": 0,
        "migration_steps": [
            "map_census_row_into_typed_RECORD_KEYS",
            "rebuild_authority_packet_group_membership",
            "add_composition_binding_to_sealed_destination",
            "delegate_plane_validators_after_reconstruction",
        ],
        "code_fixture_touches_proxy": {
            "native_schema_rewrites": 1,
            "adapter_modules": 1,
            "fixture_records_requiring_typed_reshape": 1,
            "fixture_records_touched": 1,
        },
    }


def _measure_receipt_latency(
    arm: type[ab.LayeredBridge] | type[ab.UnifiedTypedRegistry],
    envelope: Mapping[str, Any],
    *,
    rounds: int = 40,
) -> dict[str, Any]:
    encoded = [copy.deepcopy(dict(envelope))]
    for _ in range(3):
        arm.validate(encoded[0])
        arm.lookup_index(encoded[0])
    gc.collect()

    validate_ms: list[float] = []
    serialize_ms: list[float] = []
    lookup_ms: list[float] = []
    for _ in range(rounds):
        start = time.perf_counter_ns()
        arm.validate(encoded[0])
        validate_ms.append((time.perf_counter_ns() - start) / 1_000_000.0)

        start = time.perf_counter_ns()
        payload = ab._canonical_bytes(encoded[0])
        serialize_ms.append((time.perf_counter_ns() - start) / 1_000_000.0)
        _ = len(payload)

        start = time.perf_counter_ns()
        index = arm.lookup_index(encoded[0])
        rows = index.get(("item77_receipt", "cheap_route_example"))
        if not rows:
            raise ab.ArchitectureError("item77_lookup_miss")
        lookup_ms.append((time.perf_counter_ns() - start) / 1_000_000.0)

    validate = ab._distribution(validate_ms, "ms_per_receipt_validate")
    serialize = ab._distribution(serialize_ms, "ms_per_receipt_serialize")
    lookup = ab._distribution(lookup_ms, "ms_per_receipt_lookup")
    for dist in (validate, serialize, lookup):
        cv = dist.get("coefficient_of_variation")
        dist["low_signal"] = bool(
            (cv is not None and float(cv) > MATERIAL["latency_cv_signal_floor"])
            or float(dist["p50"]) < MATERIAL["min_validation_ms_p50"]
        )
    return {
        "rounds": rounds,
        "warmup_rounds": 3,
        "validate": validate,
        "serialize": serialize,
        "lookup": lookup,
        "timer": "time.perf_counter_ns",
        "timer_resolution_s": time.get_clock_info("perf_counter").resolution,
    }


def _provenance_and_seal_checks(
    *,
    arm_name: str,
    logical: Mapping[str, Any],
    decoded: Mapping[str, Any],
    source_row: Mapping[str, Any],
) -> dict[str, Any]:
    records = [
        record
        for record in decoded["records"]
        if record.get("plane") == "item77_receipt"
    ]
    missing: list[str] = []
    if len(records) != 1:
        missing.append(f"item77_record_count:{len(records)}")
        return {
            "arm": arm_name,
            "hard_fail": True,
            "missing": missing,
            "provenance_preserved": False,
            "seal_preserved": False,
        }
    record = records[0]
    value = record.get("value")
    if not isinstance(value, Mapping):
        missing.append("item77_value_not_mapping")
        return {
            "arm": arm_name,
            "hard_fail": True,
            "missing": missing,
            "provenance_preserved": False,
            "seal_preserved": False,
        }

    for key in ab.ITEM77_FIELDS:
        if key not in value:
            missing.append(f"value_field_missing:{key}")
        elif ab._canonical_bytes(value.get(key)) != ab._canonical_bytes(
            source_row.get(key)
        ):
            missing.append(f"value_field_drift:{key}")

    for key in ("source", "authority"):
        if record.get(key) is None:
            missing.append(f"record_{key}_missing")
    prov = record.get("provenance")
    if not isinstance(prov, Mapping):
        missing.append("provenance_missing")
    else:
        for key in ("source_path", "source_sha256", "fixture_id"):
            if not prov.get(key):
                missing.append(f"provenance_{key}_missing")
        if prov.get("measurement_only") is not True:
            missing.append("provenance_measurement_only_lost")

    for key in ("survivor_hash", "policy_mode", "rid_state", "plant_state"):
        if key not in value:
            missing.append(f"provenance_carrier_missing:{key}")

    seal_issues: list[str] = []
    expected_dest = _destination_binding(source_row)
    binding_dest = (record.get("binding") or {}).get("destination")
    if ab._canonical_bytes(binding_dest) != ab._canonical_bytes(expected_dest):
        seal_issues.append("binding_destination_mismatch")
    composition = decoded.get("composition") or []
    if not composition:
        seal_issues.append("composition_missing")
    else:
        if ab._canonical_bytes(composition[0].get("destination")) != ab._canonical_bytes(
            expected_dest
        ):
            seal_issues.append("composition_destination_mismatch")
    if value.get("destination_match") != source_row.get("destination_match"):
        seal_issues.append("destination_match_drift")
    if ab._canonical_bytes(value.get("raw_route")) != ab._canonical_bytes(
        source_row.get("raw_route")
    ):
        seal_issues.append("raw_route_drift")
    if ab._canonical_bytes(value.get("final_route")) != ab._canonical_bytes(
        source_row.get("final_route")
    ):
        seal_issues.append("final_route_drift")
    # No invented binding: composition must reference the real record id.
    if composition and composition[0].get("record_id") != record.get("record_id"):
        seal_issues.append("invented_or_mismatched_binding_record_id")

    # Roundtrip fidelity of the whole logical bundle.
    if ab._canonical_bytes(decoded) != ab._canonical_bytes(ab._normalize_bundle(logical)):
        missing.append("logical_roundtrip_drift")

    provenance_ok = not any(
        item.startswith("value_field_")
        or item.startswith("provenance")
        or item.startswith("record_")
        or item.startswith("provenance_carrier")
        for item in missing
    ) and not missing
    # tighter: provenance_ok if no provenance-related misses
    provenance_fail = [
        item
        for item in missing
        if item.startswith(
            (
                "value_field_",
                "provenance",
                "record_source",
                "record_authority",
                "provenance_carrier",
            )
        )
        or item in {"item77_value_not_mapping", "logical_roundtrip_drift"}
        or item.startswith("item77_record_count")
    ]
    seal_fail = seal_issues or any(
        item.startswith("value_field_drift:sealed")
        or item.startswith("value_field_drift:destination")
        or item.startswith("value_field_drift:raw_route")
        or item.startswith("value_field_drift:final_route")
        for item in missing
    )
    hard_fail = bool(provenance_fail or seal_fail)
    return {
        "arm": arm_name,
        "hard_fail": hard_fail,
        "missing": missing,
        "seal_issues": seal_issues,
        "provenance_preserved": not provenance_fail,
        "seal_preserved": not seal_fail,
        "provenance_keys_checked": list(PROVENANCE_KEYS),
        "seal_keys_checked": list(SEAL_KEYS),
        "binding_destination": binding_dest,
        "expected_destination": expected_dest,
    }


def _appendix5_removal_test(
    arm: type[ab.LayeredBridge] | type[ab.UnifiedTypedRegistry],
    envelope: Mapping[str, Any],
) -> dict[str, Any]:
    """Appendix-5 style drop-adapter test: removing bridge/registry must fail closed."""

    mutated = copy.deepcopy(dict(envelope))
    removed = "bridge" if arm.name == ARM_A else "registry"
    mutated.pop(removed, None)
    error: str | None = None
    try:
        arm.validate(mutated)
        rejected = False
    except Exception as exc:  # noqa: BLE001 - fail-closed evidence
        rejected = True
        error = f"{type(exc).__name__}:{exc}"
    residue_keys = sorted(set(mutated) - {"schema_version", "bundle_id", "draft"})
    return {
        "removed_component": removed,
        "validator_rejected_removal": rejected,
        "error": error,
        "rollback_clean": rejected,
        "residue_keys_after_removal": residue_keys,
        "appendix_five_proxy": (
            "Dropping the candidate adapter component must make validation fail; "
            "no silent acceptance of a partial envelope."
        ),
    }


def _pct_advantage(baseline: float, challenger: float) -> float:
    if baseline <= 0:
        return 0.0
    return ((baseline - challenger) / baseline) * 100.0


def _decide(
    arm_metrics: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    a = arm_metrics[ARM_A]
    b = arm_metrics[ARM_B]
    thresholds = copy.deepcopy(MATERIAL)
    reasons: list[str] = []

    a_gate = a["hard_gate"]
    b_gate = b["hard_gate"]
    if a_gate["status"] != "PASS" and b_gate["status"] != "PASS":
        return {
            "verdict": "INCONCLUSIVE",
            "material_advantage": False,
            "thresholds": thresholds,
            "reasons": ["both_arms_hard_gate_fail"],
            "promote": None,
        }
    if a_gate["status"] != "PASS" and b_gate["status"] == "PASS":
        return {
            "verdict": "UNIFIED_TYPED_REGISTRY_WINS_PILOT",
            "material_advantage": True,
            "thresholds": thresholds,
            "reasons": ["layered_bridge_hard_gate_fail"],
            "promote": None,
            "note": "Operational win on hard-gate only; still no production promotion.",
        }
    if b_gate["status"] != "PASS" and a_gate["status"] == "PASS":
        return {
            "verdict": "LAYERED_BRIDGE_WINS_PILOT",
            "material_advantage": True,
            "thresholds": thresholds,
            "reasons": ["unified_typed_registry_hard_gate_fail"],
            "promote": None,
            "note": "Operational win on hard-gate only; still no production promotion.",
        }

    # Migration / adapter touches
    a_touches = int(a["migration"]["code_fixture_touches_proxy"]["fixture_records_touched"])
    b_touches = int(b["migration"]["code_fixture_touches_proxy"]["fixture_records_touched"])
    a_rewrites = int(a["migration"]["code_fixture_touches_proxy"]["native_schema_rewrites"])
    b_rewrites = int(b["migration"]["code_fixture_touches_proxy"]["native_schema_rewrites"])
    a_steps = len(a["migration"]["migration_steps"])
    b_steps = len(b["migration"]["migration_steps"])
    a_risk = a_rewrites + int(a["migration"]["adapter_touches"]["packet_seal_reconstruction"])
    b_risk = b_rewrites + int(b["migration"]["adapter_touches"]["packet_seal_reconstruction"])

    adapter_ratio_b_over_a = (b_steps / a_steps) if a_steps else 0.0
    adapter_ratio_a_over_b = (a_steps / b_steps) if b_steps else 0.0

    # Latency / bytes (lower is better)
    a_bytes = float(a["storage"]["serialized_bytes"])
    b_bytes = float(b["storage"]["serialized_bytes"])
    a_lat = float(a["latency"]["validate"]["p50"])
    b_lat = float(b["latency"]["validate"]["p50"])
    a_lat_low = bool(a["latency"]["validate"]["low_signal"])
    b_lat_low = bool(b["latency"]["validate"]["low_signal"])
    latency_comparable = not (a_lat_low or b_lat_low)

    byte_adv_b = _pct_advantage(a_bytes, b_bytes)
    byte_adv_a = _pct_advantage(b_bytes, a_bytes)
    lat_adv_b = _pct_advantage(a_lat, b_lat) if latency_comparable else 0.0
    lat_adv_a = _pct_advantage(b_lat, a_lat) if latency_comparable else 0.0

    material = False
    verdict = "TIE_WITH_CONSTRAINTS"

    # Prefer lower migration risk; do not award efficiency if risk increases.
    if (
        adapter_ratio_b_over_a >= thresholds["adapter_touch_ratio"]
        and b_risk <= a_risk
        and b_gate["semantic_ambiguity"] == 0
    ):
        # A has materially fewer migration steps
        material = True
        verdict = "LAYERED_BRIDGE_WINS_PILOT"
        reasons.append(
            f"adapter_steps_ratio_b/a={adapter_ratio_b_over_a:.2f}>="
            f"{thresholds['adapter_touch_ratio']}"
        )
    elif (
        adapter_ratio_a_over_b >= thresholds["adapter_touch_ratio"]
        and a_risk <= b_risk
        and a_gate["semantic_ambiguity"] == 0
    ):
        material = True
        verdict = "UNIFIED_TYPED_REGISTRY_WINS_PILOT"
        reasons.append(
            f"adapter_steps_ratio_a/b={adapter_ratio_a_over_b:.2f}>="
            f"{thresholds['adapter_touch_ratio']}"
        )

    need = thresholds["serialized_byte_and_latency_pct"]
    if not material and latency_comparable:
        if (
            byte_adv_b >= need
            and lat_adv_b >= need
            and b_risk <= a_risk
            and b_gate["semantic_ambiguity"] == 0
        ):
            material = True
            verdict = "UNIFIED_TYPED_REGISTRY_WINS_PILOT"
            reasons.append(
                f"typed_registry_bytes+latency_adv>={need}% "
                f"(bytes={byte_adv_b:.1f}, latency={lat_adv_b:.1f})"
            )
        elif (
            byte_adv_a >= need
            and lat_adv_a >= need
            and a_risk <= b_risk
            and a_gate["semantic_ambiguity"] == 0
        ):
            material = True
            verdict = "LAYERED_BRIDGE_WINS_PILOT"
            reasons.append(
                f"layered_bridge_bytes+latency_adv>={need}% "
                f"(bytes={byte_adv_a:.1f}, latency={lat_adv_a:.1f})"
            )

    if not material:
        reasons.append("differences_below_material_threshold_or_risk_tradeoff")
        if a_risk < b_risk:
            reasons.append(
                "layered_bridge_lower_migration_surface_but_not_alone_material_under_rule"
            )
        if b_bytes < a_bytes or (latency_comparable and b_lat < a_lat):
            reasons.append(
                "typed_registry_smaller_or_faster_but_not_alone_material_under_rule"
            )
        if not latency_comparable:
            reasons.append("latency_low_signal_excluded_from_material_efficiency_rule")

    return {
        "verdict": verdict,
        "material_advantage": material,
        "thresholds": thresholds,
        "reasons": reasons,
        "promote": None,
        "comparisons": {
            "migration_steps": {ARM_A: a_steps, ARM_B: b_steps},
            "adapter_touch_ratio_b_over_a": adapter_ratio_b_over_a,
            "native_schema_rewrites": {ARM_A: a_rewrites, ARM_B: b_rewrites},
            "migration_risk_proxy": {ARM_A: a_risk, ARM_B: b_risk},
            "fixture_records_touched": {ARM_A: a_touches, ARM_B: b_touches},
            "serialized_bytes": {ARM_A: a_bytes, ARM_B: b_bytes},
            "validate_p50_ms": {ARM_A: a_lat, ARM_B: b_lat},
            "byte_advantage_pct_b_vs_a": byte_adv_b,
            "latency_advantage_pct_b_vs_a": lat_adv_b,
            "latency_comparable": latency_comparable,
        },
        "note": (
            "Promote neither architecture by default. A pilot win is evidence only."
            if material
            else "Keep prior TIE_WITH_CONSTRAINTS posture; defer architecture choice."
        ),
    }


def evaluate_arm(
    arm: type[ab.LayeredBridge] | type[ab.UnifiedTypedRegistry],
    *,
    bundle: Mapping[str, Any],
    source_row: Mapping[str, Any],
) -> dict[str, Any]:
    envelope = arm.encode(bundle)
    arm.validate(envelope)
    decoded = arm.decode(envelope)
    checks = _provenance_and_seal_checks(
        arm_name=arm.name,
        logical=bundle,
        decoded=decoded,
        source_row=source_row,
    )
    migration = _count_field_remaps(arm.name, envelope, source_row)
    latency = _measure_receipt_latency(arm, envelope)
    removal = _appendix5_removal_test(arm, envelope)
    payload = ab._canonical_bytes(envelope)
    item_records = [
        record
        for record in decoded["records"]
        if record.get("plane") == "item77_receipt"
    ]
    lookup = arm.lookup_index(envelope)
    ambiguous = any(len(rows) > 1 for rows in lookup.values())
    hard_gate = {
        "status": (
            "PASS"
            if (
                not checks["hard_fail"]
                and removal["validator_rejected_removal"]
                and not ambiguous
            )
            else "FAIL"
        ),
        "seal_preserved": checks["seal_preserved"],
        "provenance_preserved": checks["provenance_preserved"],
        "removal_rejected": removal["validator_rejected_removal"],
        "semantic_ambiguity": int(ambiguous),
        "roundtrip_ok": "logical_roundtrip_drift" not in checks["missing"],
    }
    return {
        "candidate": arm.name,
        "schema_version": arm.schema_version,
        "hard_gate": hard_gate,
        "checks": checks,
        "migration": migration,
        "latency": latency,
        "removal_test": removal,
        "storage": {
            "serialized_bytes": len(payload),
            "serialization_sha256": hashlib.sha256(payload).hexdigest(),
            "item77_records": len(item_records),
        },
        "determinism": {
            "hashes": [
                hashlib.sha256(ab._canonical_bytes(arm.encode(bundle))).hexdigest()
                for _ in range(3)
            ],
        },
    }


def evaluate_secondary_seal_observation(
    arms: Sequence[type[ab.LayeredBridge] | type[ab.UnifiedTypedRegistry]],
    *,
    source_hashes: Mapping[str, Mapping[str, str]],
    census_path: Path,
    census_sha: str,
    secondary: Mapping[str, Any],
) -> dict[str, Any]:
    row = secondary["row"]
    bundle = build_single_receipt_bundle(
        source_hashes=source_hashes,
        census_path=census_path,
        census_sha=census_sha,
        row=row,
        role="seal_fail_obs",
    )
    out: dict[str, Any] = {
        "role": secondary["role"],
        "note": secondary["note"],
        "example_id": secondary["example_id"],
        "policy_mode": secondary["policy_mode"],
        "destination_match": secondary["destination_match"],
        "row_sha256": secondary["row_sha256"],
        "arms": {},
    }
    for arm in arms:
        envelope = arm.encode(bundle)
        arm.validate(envelope)
        decoded = arm.decode(envelope)
        checks = _provenance_and_seal_checks(
            arm_name=arm.name,
            logical=bundle,
            decoded=decoded,
            source_row=row,
        )
        # For failure-mode rows, destination_match=false must be preserved, not flipped.
        item = next(
            record
            for record in decoded["records"]
            if record.get("plane") == "item77_receipt"
        )
        value = item.get("value")
        out["arms"][arm.name] = {
            "hard_fail": checks["hard_fail"],
            "seal_preserved": checks["seal_preserved"],
            "provenance_preserved": checks["provenance_preserved"],
            "destination_match_preserved": (
                isinstance(value, Mapping) and value.get("destination_match") is False
            ),
            "missing": checks["missing"],
            "seal_issues": checks["seal_issues"],
        }
    return out


def _markdown(report: Mapping[str, Any]) -> str:
    primary = report["selected_receipt"]["primary"]
    decision = report["decision"]
    metrics = report["metrics_table"]
    lines = [
        f"# {EXPERIMENT_ID}",
        "",
        f"- Schema: `{SCHEMA_VERSION}`",
        f"- Prior A/B: `{PRIOR_EXPERIMENT_ID}` / `{report['prior_ab']['verdict']}`",
        f"- Verdict: **{decision['verdict']}**",
        f"- Material advantage: `{decision['material_advantage']}`",
        f"- Promote: `{decision['promote']}`",
        "",
        "## Material-advantage thresholds",
        "",
        (
            f"- Adapter/migration steps ratio ≥ **{MATERIAL['adapter_touch_ratio']}×** "
            "with no migration-risk increase and zero semantic ambiguity"
        ),
        (
            f"- Or ≥ **{MATERIAL['serialized_byte_and_latency_pct']}%** serialized-byte "
            "**and** validate-latency advantage with zero migration-risk increase"
        ),
        "- Or clear seal/provenance hard-gate failure on exactly one arm",
        "- Seal-first: any seal/destination/provenance loss is a hard fail for that arm",
        "",
        "## Selected receipt",
        "",
        f"- Census: `{report['selected_receipt']['census_path']}`",
        f"- Census sha256: `{report['selected_receipt']['census_sha256']}`",
        f"- Example: `{primary['example_id']}`",
        f"- Mode: `{primary['policy_mode']}`",
        f"- Row sha256: `{primary['row_sha256']}`",
        f"- Selection score/reasons: `{primary['selection_score']}` / `{primary['selection_reasons']}`",
        f"- Fields bound: `{', '.join(primary['fields_bound'])}`",
        "",
        "## Metrics",
        "",
        "| Metric | LAYERED_BRIDGE | UNIFIED_TYPED_REGISTRY |",
        "| --- | --- | --- |",
    ]
    for row in metrics:
        lines.append(
            f"| {row['metric']} | {row[ARM_A]} | {row[ARM_B]} |"
        )
    lines.extend(
        [
            "",
            "## Hard gates",
            "",
            f"- LAYERED_BRIDGE: **{report['arms'][ARM_A]['hard_gate']['status']}**",
            f"- UNIFIED_TYPED_REGISTRY: **{report['arms'][ARM_B]['hard_gate']['status']}**",
            "",
            "## Decision reasons",
            "",
        ]
    )
    for reason in decision["reasons"]:
        lines.append(f"- {reason}")
    if report.get("secondary_seal_observation"):
        sec = report["secondary_seal_observation"]
        lines.extend(
            [
                "",
                "## Secondary seal-failure observation",
                "",
                f"- Example: `{sec['example_id']}` mode `{sec['policy_mode']}`",
                f"- Note: {sec['note']}",
            ]
        )
        for arm_name, arm_row in sec["arms"].items():
            lines.append(
                f"- {arm_name}: seal_preserved=`{arm_row['seal_preserved']}` "
                f"destination_match_preserved=`{arm_row['destination_match_preserved']}` "
                f"hard_fail=`{arm_row['hard_fail']}`"
            )
    lines.extend(
        [
            "",
            "## Mutation guard",
            "",
            f"- Status: **{report['mutation_guard']['status']}**",
            f"- Census unchanged: `{report['mutation_guard']['census_unchanged']}`",
            f"- Survivor checkpoint unchanged: `{report['mutation_guard']['survivor_unchanged']}`",
            "",
            "## Reproducible command",
            "",
            "```powershell",
            report["run"]["exact_command"],
            "```",
            "",
            "## Limitations",
            "",
        ]
    )
    for item in report["limitations"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Recommended next action",
            "",
            report["recommended_next_action"],
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def run_pilot(
    *,
    census_path: Path,
    output_root: Path | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    started = _utc_now()
    before_census = _file_fingerprint(census_path)
    payload, rows, supplemental = _load_census(census_path)
    survivor_hash = str(supplemental.get("survivor_hash") or "")
    checkpoint = payload.get("checkpoint_identity") or {}
    survivor_path = None
    if isinstance(checkpoint, Mapping):
        after = checkpoint.get("after")
        if isinstance(after, Mapping) and after.get("path"):
            survivor_path = Path(str(after["path"]))
    before_survivor = (
        _file_fingerprint(survivor_path)
        if survivor_path is not None and survivor_path.is_file()
        else None
    )

    primary_row, primary_meta, secondary = select_receipts(rows)
    source_hashes = ab._source_hashes()
    bundle = build_single_receipt_bundle(
        source_hashes=source_hashes,
        census_path=census_path,
        census_sha=before_census["sha256"],
        row=primary_row,
        role="primary",
    )

    arm_a = evaluate_arm(ab.LayeredBridge, bundle=bundle, source_row=primary_row)
    arm_b = evaluate_arm(
        ab.UnifiedTypedRegistry, bundle=bundle, source_row=primary_row
    )
    secondary_report = None
    if secondary is not None:
        secondary_report = evaluate_secondary_seal_observation(
            (ab.LayeredBridge, ab.UnifiedTypedRegistry),
            source_hashes=source_hashes,
            census_path=census_path,
            census_sha=before_census["sha256"],
            secondary=secondary,
        )

    decision = _decide({ARM_A: arm_a, ARM_B: arm_b})
    metrics_table = [
        {
            "metric": "hard_gate",
            ARM_A: arm_a["hard_gate"]["status"],
            ARM_B: arm_b["hard_gate"]["status"],
        },
        {
            "metric": "seal_preserved",
            ARM_A: arm_a["hard_gate"]["seal_preserved"],
            ARM_B: arm_b["hard_gate"]["seal_preserved"],
        },
        {
            "metric": "provenance_preserved",
            ARM_A: arm_a["hard_gate"]["provenance_preserved"],
            ARM_B: arm_b["hard_gate"]["provenance_preserved"],
        },
        {
            "metric": "migration_steps",
            ARM_A: len(arm_a["migration"]["migration_steps"]),
            ARM_B: len(arm_b["migration"]["migration_steps"]),
        },
        {
            "metric": "native_schema_rewrites",
            ARM_A: arm_a["migration"]["code_fixture_touches_proxy"][
                "native_schema_rewrites"
            ],
            ARM_B: arm_b["migration"]["code_fixture_touches_proxy"][
                "native_schema_rewrites"
            ],
        },
        {
            "metric": "field_remaps_proxy",
            ARM_A: arm_a["migration"]["field_remaps"],
            ARM_B: arm_b["migration"]["field_remaps"],
        },
        {
            "metric": "packet_seal_reconstruction_required",
            ARM_A: arm_a["migration"]["adapter_touches"][
                "packet_seal_reconstruction"
            ],
            ARM_B: arm_b["migration"]["adapter_touches"][
                "packet_seal_reconstruction"
            ],
        },
        {
            "metric": "serialized_bytes",
            ARM_A: arm_a["storage"]["serialized_bytes"],
            ARM_B: arm_b["storage"]["serialized_bytes"],
        },
        {
            "metric": "validate_p50_ms",
            ARM_A: arm_a["latency"]["validate"]["p50"],
            ARM_B: arm_b["latency"]["validate"]["p50"],
        },
        {
            "metric": "serialize_p50_ms",
            ARM_A: arm_a["latency"]["serialize"]["p50"],
            ARM_B: arm_b["latency"]["serialize"]["p50"],
        },
        {
            "metric": "lookup_p50_ms",
            ARM_A: arm_a["latency"]["lookup"]["p50"],
            ARM_B: arm_b["latency"]["lookup"]["p50"],
        },
        {
            "metric": "appendix5_removal_rejected",
            ARM_A: arm_a["removal_test"]["validator_rejected_removal"],
            ARM_B: arm_b["removal_test"]["validator_rejected_removal"],
        },
    ]

    after_census = _file_fingerprint(census_path)
    after_survivor = (
        _file_fingerprint(survivor_path)
        if survivor_path is not None and survivor_path.is_file()
        else None
    )
    census_unchanged = after_census == before_census
    survivor_unchanged = before_survivor == after_survivor
    mutation_guard = {
        "status": "PASS" if census_unchanged and survivor_unchanged else "FAIL",
        "census_before": before_census,
        "census_after": after_census,
        "census_unchanged": census_unchanged,
        "survivor_path": (
            str(survivor_path).replace("\\", "/") if survivor_path else None
        ),
        "survivor_before": before_survivor,
        "survivor_after": after_survivor,
        "survivor_unchanged": survivor_unchanged,
        "survivor_hash": survivor_hash,
    }

    finished = _utc_now()
    command = (
        f"L:\\Continue\\.venv\\Scripts\\python.exe "
        f"{Path(__file__).resolve().as_posix()} --run "
        f"--census {census_path.as_posix()}"
    )
    prior_path = (
        FOUNDATION
        / "artifacts"
        / "auto"
        / "tag_architecture_ab_v1"
        / "20260807T083432Z"
        / "tag_architecture_ab_v1_20260807T083432Z.json"
    )
    prior_verdict = None
    if prior_path.is_file():
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        prior_verdict = prior.get("verdict")

    recommended = (
        "Defer architecture choice; retain TIE_WITH_CONSTRAINTS. No second receipt "
        "class required unless operator wants a non-LIT federation sealed row as a "
        "follow-up observation (not a promotion gate)."
        if decision["verdict"] == "TIE_WITH_CONSTRAINTS"
        else (
            "Pilot showed a material operational difference under the declared "
            "thresholds, but do not promote either architecture to production. "
            "Operator review required before any schema/router change."
            if decision["material_advantage"]
            else "Mark inconclusive and rerun only if measurement signal improves."
        )
    )

    report: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "schema_version": SCHEMA_VERSION,
        "prior_ab": {
            "experiment_id": PRIOR_EXPERIMENT_ID,
            "report": str(prior_path).replace("\\", "/") if prior_path.is_file() else None,
            "verdict": prior_verdict,
        },
        "arms": {ARM_A: arm_a, ARM_B: arm_b},
        "selected_receipt": {
            "census_path": str(census_path).replace("\\", "/"),
            "census_sha256": before_census["sha256"],
            "prompt_manifest_path": supplemental.get("prompt_manifest_path"),
            "prompt_manifest_sha256": supplemental.get("prompt_manifest_sha256"),
            "survivor_hash": survivor_hash,
            "primary": {
                key: value
                for key, value in primary_meta.items()
                if key != "row"
            },
            "primary_row": primary_row,
            "secondary_included": secondary is not None,
        },
        "secondary_seal_observation": secondary_report,
        "metrics_table": metrics_table,
        "decision": decision,
        "verdict": decision["verdict"],
        "material_thresholds": MATERIAL,
        "mutation_guard": mutation_guard,
        "naming_policy": {
            "item77_receipt": "proposed_operator_gated_not_established_fact",
            "cheap_route_example": "proposed_operator_gated_not_established_fact",
        },
        "run": {
            "started_at": _utc_text(started),
            "finished_at": _utc_text(finished),
            "duration_seconds": (finished - started).total_seconds(),
            "python_executable": str(Path(sys.executable)).replace("\\", "/"),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "pid": os.getpid(),
            "exact_command": command,
        },
        "limitations": [
            "Single-receipt pilot only; not a multi-window architecture bakeoff.",
            "Migration step / rewrite counts are explicit proxies for this binding, not full production cutover estimates.",
            "Latency is local Python timing; low-signal distributions are excluded from the material efficiency rule.",
            "Experiment-only names item77_receipt / cheap_route_example remain proposed and operator-gated.",
            "No production schema promotion, router change, training, or checkpoint mutation was performed.",
        ],
        "recommended_next_action": recommended,
        "promotion": {
            "LAYERED_BRIDGE": False,
            "UNIFIED_TYPED_REGISTRY": False,
            "any_production_schema": False,
        },
    }

    timestamp = finished.strftime("%Y%m%dT%H%M%SZ")
    out_dir = (
        output_root
        if output_root is not None
        else FOUNDATION
        / "artifacts"
        / "auto"
        / "tag_architecture_ab_v1"
        / timestamp
    )
    out_dir.mkdir(parents=True, exist_ok=False)
    json_path = out_dir / f"tag_receipt_boundary_pilot_v1_{timestamp}.json"
    md_path = out_dir / f"tag_receipt_boundary_pilot_v1_{timestamp}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    md_path.write_text(_markdown(report), encoding="utf-8", newline="\n")
    return report, json_path, md_path


def run_selftest() -> dict[str, Any]:
    source_hashes = ab._source_hashes()
    synthetic = {
        "survivor_hash": "0" * 64,
        "prompt": "selftest",
        "source": {
            "template_id": "selftest",
            "template_source": "selftest",
            "example_id": "SC77-SELF",
        },
        "sealed_destination": {"target_char": "e", "target_token_id": 70},
        "destination_match": True,
        "policy_mode": {
            "mode": "prefer_efficient_snap",
            "policy": "thermal_efficient",
            "post_snap": True,
        },
        "raw_route": "80",
        "final_route": "70",
        "uml_domains": [],
        "federation": "LIT",
        "kind": "valid_efficient",
        "cost": 1,
        "error": 0.0,
        "cheapest": "70",
        "rid_state": {"available": True, "master_s_n": 0.9, "source": "selftest"},
        "plant_state": {"available": True, "master_s_n": 0.9, "source": "selftest"},
    }
    bundle = build_single_receipt_bundle(
        source_hashes=source_hashes,
        census_path=DEFAULT_CENSUS,
        census_sha="a" * 64,
        row=synthetic,
        role="selftest",
    )
    checks: list[str] = []
    for arm in (ab.LayeredBridge, ab.UnifiedTypedRegistry):
        result = evaluate_arm(arm, bundle=bundle, source_row=synthetic)
        if result["hard_gate"]["status"] != "PASS":
            raise ab.ArchitectureError(f"selftest_hard_gate:{arm.name}:{result}")
        checks.append(f"{arm.name}:pass")
        hashes = result["determinism"]["hashes"]
        if len(set(hashes)) != 1:
            raise ab.ArchitectureError(f"selftest_determinism:{arm.name}")
        checks.append(f"{arm.name}:determinism")
    # Selection prefers sealed raw≠final.
    sealed, fail = dict(synthetic), dict(synthetic)
    fail["destination_match"] = False
    fail["policy_mode"] = {"mode": "raw_no_snap", "policy": None, "post_snap": False}
    primary, primary_meta, secondary = select_receipts([sealed, fail])
    if primary.get("destination_match") is not True:
        raise ab.ArchitectureError("selftest_primary_not_sealed")
    if secondary is None or secondary.get("destination_match") is not False:
        raise ab.ArchitectureError("selftest_secondary_missing")
    checks.extend(["select_primary", "select_secondary"])
    return {
        "ok": True,
        "experiment_id": EXPERIMENT_ID,
        "checks": len(checks),
        "details": checks,
        "primary_meta": {
            key: primary_meta[key]
            for key in ("example_id", "policy_mode", "selection_score")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selftest", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args()
    if args.selftest:
        result = run_selftest()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    report, json_path, md_path = run_pilot(
        census_path=args.census,
        output_root=args.output_root,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "experiment_id": EXPERIMENT_ID,
                "verdict": report["verdict"],
                "material_advantage": report["decision"]["material_advantage"],
                "promote": report["decision"]["promote"],
                "primary_example_id": report["selected_receipt"]["primary"][
                    "example_id"
                ],
                "primary_mode": report["selected_receipt"]["primary"]["policy_mode"],
                "mutation_guard": report["mutation_guard"]["status"],
                "json_report": str(json_path).replace("\\", "/"),
                "markdown_report": str(md_path).replace("\\", "/"),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
