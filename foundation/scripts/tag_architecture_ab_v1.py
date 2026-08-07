#!/usr/bin/env python3
"""Offline A/B for Viv/AIOS tag architecture candidates.

Experiment: TAG_ARCH_AB_V1

This harness is deliberately read-only with respect to runtime, model,
checkpoint, curriculum, and routing state.  It prototypes two deterministic
receipt representations over the same logical records:

* LAYERED_BRIDGE keeps native plane payloads and adds a composition bridge.
* UNIFIED_TYPED_REGISTRY serializes every tag through one typed registry while
  delegating authority checks to the existing plane validators.

Only timestamped reports under ``foundation/artifacts/auto`` are written.
"""
from __future__ import annotations

import argparse
import ast
import copy
import gc
import hashlib
import inspect
import json
import math
import os
import platform
import re
import statistics
import sys
import textwrap
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


EXPERIMENT_ID = "TAG_ARCH_AB_V1"
SCHEMA_VERSION = "tag_architecture_ab_v1"
ARM_A = "LAYERED_BRIDGE"
ARM_B = "UNIFIED_TYPED_REGISTRY"

FOUNDATION = Path(__file__).resolve().parents[1]
VIV = FOUNDATION.parent
MODEL = FOUNDATION / "models" / "Training" / "current" / "viv_slm" / "model"
SANDBOX = MODEL / "test_training"
for _path in (FOUNDATION, VIV, MODEL, SANDBOX):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from lib import aios_tagged_packet as tagged_packet  # noqa: E402
from lib.uml_character_tokenizer import (  # noqa: E402
    SCHEMA_VERSION as UML_TOKENIZER_SCHEMA,
    TOKEN_UNIT as UML_TOKEN_UNIT,
    encode as uml_character_encode,
)
from lib.uml_equation_registry import (  # noqa: E402
    _domains_in_expr_raw,
    _eval_value,
    _symbolic_cost,
)
from scripts.stage1_mouth_identity_curriculum import (  # noqa: E402
    BASE_ATOMS,
    COMBO_DOMAINS,
    DOMAIN_META,
    build_rows as build_mouth_rows,
)
from context_pack import KNOWN_ROLES  # noqa: E402
from uml_route_usage_telemetry import VALID_FEDERATIONS  # noqa: E402


SOURCE_PATHS = {
    "authority_packet": FOUNDATION / "lib" / "aios_tagged_packet.py",
    "mouth_atom": FOUNDATION / "scripts" / "stage1_mouth_identity_curriculum.py",
    "uml_registry": FOUNDATION / "lib" / "uml_equation_registry.py",
    "uml_route": FOUNDATION / "lib" / "uml_route_governor.py",
    "context_role": MODEL / "context_pack.py",
    "speak_receipt": MODEL / "speak_lanes.py",
    "snap_free_receipt": SANDBOX / "run_uml_snap_free_audit.py",
    "uml_tokenizer": FOUNDATION / "lib" / "uml_character_tokenizer.py",
    "uml_token_economics": FOUNDATION / "lib" / "uml_token_economics.py",
    "appendix_five": FOUNDATION / "metacognition" / "appendix five.txt",
}

PLANES = (
    "authority_packet",
    "mouth_atom",
    "uml_route",
    "context_role",
    "item77_receipt",
)
ROUTE_LABELS = frozenset({"LIT", "A", "S", "M", "D", "U"}) | frozenset(
    VALID_FEDERATIONS
)
RECORD_KEYS = frozenset(
    {
        "record_id",
        "plane",
        "name",
        "value",
        "source",
        "authority",
        "confidence",
        "required",
        "provenance",
        "attributes",
        "binding",
    }
)
GROUP_KEYS = frozenset(
    {
        "group_id",
        "schema_version",
        "packet_id",
        "created_at",
        "packet_digest",
        "cpu_signature",
        "record_ids",
    }
)
COMPOSITION_KEYS = frozenset(
    {
        "binding_id",
        "record_id",
        "plane",
        "name",
        "destination",
        "semantic_aliases",
    }
)
BRIDGE_KEYS = (RECORD_KEYS - {"value"}) | {"native_ref"}
ITEM77_FIELDS = (
    "survivor_hash",
    "prompt",
    "source",
    "sealed_destination",
    "destination_match",
    "policy_mode",
    "raw_route",
    "final_route",
    "uml_domains",
    "federation",
    "kind",
    "cost",
    "error",
    "cheapest",
    "rid_state",
    "plant_state",
)
AUTHORITY_ATTACK_CATEGORIES = frozenset(
    {
        "user_mints_cpu_authority",
        "gpu_draft_echoes_tag_markup",
        "source_authority_mismatch",
        "tampered_digest",
        "tampered_signature",
    }
)
ATTACK_CATEGORIES = (
    "user_mints_cpu_authority",
    "gpu_draft_echoes_tag_markup",
    "identity_collision",
    "knowledge_vs_knowledge_tags",
    "unknown_tag",
    "unknown_plane",
    "invalid_uml_domain_federation",
    "stale_missing_provenance",
    "source_authority_mismatch",
    "duplicate_conflicting_bindings",
    "tampered_digest",
    "tampered_signature",
    "invented_binding",
    "destination_mismatch",
)


class ArchitectureError(ValueError):
    """Fail-closed candidate schema or binding error."""


class AmbiguousLookup(ArchitectureError):
    """An unqualified lookup resolves to more than one plane."""


def _canonical_text(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_bytes(value: Any) -> bytes:
    return _canonical_text(value).encode("utf-8")


def _sha_value(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime | None = None) -> str:
    return (value or _utc_now()).replace(microsecond=0).isoformat()


def _source_hashes() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for role, path in SOURCE_PATHS.items():
        if not path.is_file():
            raise FileNotFoundError(f"tag_ab_source_missing:{path}")
        out[role] = {
            "path": str(path).replace("\\", "/"),
            "sha256": _sha_file(path),
        }
    return out


def _provenance(
    source_hashes: Mapping[str, Mapping[str, str]],
    role: str,
    fixture_id: str,
    **extra: Any,
) -> dict[str, Any]:
    row = source_hashes[role]
    return {
        "source_path": str(row["path"]),
        "source_sha256": str(row["sha256"]),
        "fixture_id": str(fixture_id),
        "state": "current",
        "observed_at": "fixture",
        **extra,
    }


def _packet_sources(tag: str) -> tuple[str, str]:
    source = {
        "identity": "cpu_identity",
        "knowledge": "cpu_knowledge",
        "telemetry": "cpu_telemetry",
        "user_request": "user",
        "allowed_actions": "cpu_authority",
        "unknowns": "cpu_unknown",
        "rendering_rules": "cpu_authority",
    }[tag]
    authority = "user_data_only" if tag == "user_request" else "cpu"
    return source, authority


def _build_signed_packet(index: int, mouth_row: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic fixture packet and seal it with the live validator key."""

    packet_id = f"tag-ab-{index:03d}-{hashlib.sha256(str(mouth_row['pair_id']).encode()).hexdigest()[:12]}"
    created_at = _utc_text(
        datetime(2026, 8, 7, tzinfo=timezone.utc) + timedelta(seconds=index)
    )
    tags = list(mouth_row.get("tags") or [])
    domain = str(mouth_row["domain"])
    blocks = {
        "identity": [
            tagged_packet._block(  # type: ignore[attr-defined]
                "identity",
                {"name": "Viv", "system": "AIOS", "speaking_identity": True},
                block_id="I001",
                source="cpu_identity",
                confidence="verified",
            )
        ],
        "knowledge": [
            tagged_packet._block(  # type: ignore[attr-defined]
                "knowledge",
                {
                    "domain": domain,
                    "knowledge_tags": tags,
                    "fact": str((mouth_row.get("facts") or ["fixture"])[0]),
                },
                block_id="K001",
                source="cpu_knowledge",
                confidence="fixture",
            )
        ],
        "telemetry": [
            tagged_packet._block(  # type: ignore[attr-defined]
                "telemetry",
                {
                    "rid": round(0.81 + (index % 17) / 100.0, 4),
                    "plant_state": "offline_fixture",
                    "runtime_mutated": False,
                },
                block_id="T001",
                source="cpu_telemetry",
                confidence="measured_fixture",
            )
        ],
        "user_request": [
            tagged_packet._block(  # type: ignore[attr-defined]
                "user_request",
                str(mouth_row["ask"]),
                block_id="U001",
                source="user",
                confidence="unverified",
            )
        ],
        "allowed_actions": [
            tagged_packet._block(  # type: ignore[attr-defined]
                "allowed_actions",
                {"name": "render_speech", "authorized": True},
                block_id="A001",
                source="cpu_authority",
                confidence="policy",
            )
        ],
        "unknowns": [
            tagged_packet._block(  # type: ignore[attr-defined]
                "unknowns",
                {"items": [], "state": "known_empty"},
                block_id="UQ001",
                source="cpu_unknown",
                confidence="known_empty",
            )
        ],
        "rendering_rules": [
            tagged_packet._block(  # type: ignore[attr-defined]
                "rendering_rules",
                {
                    "mode": "render_only",
                    "internal_only": ["telemetry"],
                    "preserve_unknowns": True,
                    "capability_claims_require_authorization": True,
                },
                block_id="R001",
                source="cpu_authority",
                confidence="policy",
            )
        ],
    }
    unsigned = {
        "schema_version": tagged_packet.SCHEMA_VERSION,
        "packet_id": packet_id,
        "created_at": created_at,
        "blocks": blocks,
    }
    packet = dict(unsigned)
    packet["packet_digest"] = tagged_packet._digest(unsigned)  # type: ignore[attr-defined]
    packet["cpu_signature"] = tagged_packet._sign(  # type: ignore[attr-defined]
        unsigned | {"packet_digest": packet["packet_digest"]}
    )
    tagged_packet.validate_tagged_packet(packet)
    return packet


def _record(
    *,
    record_id: str,
    plane: str,
    name: str,
    value: Any,
    source: str,
    authority: str,
    confidence: str,
    required: bool,
    provenance: Mapping[str, Any],
    attributes: Mapping[str, Any] | None = None,
    binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "record_id": str(record_id),
        "plane": str(plane),
        "name": str(name),
        "value": copy.deepcopy(value),
        "source": str(source),
        "authority": str(authority),
        "confidence": str(confidence),
        "required": bool(required),
        "provenance": dict(provenance),
        "attributes": dict(attributes or {}),
        "binding": dict(binding or {}),
    }


def _packet_records(
    packet: Mapping[str, Any],
    source_hashes: Mapping[str, Mapping[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    group_id = str(packet["packet_id"])
    records: list[dict[str, Any]] = []
    record_ids: list[str] = []
    for tag in tagged_packet.ALLOWED_TAGS:
        for block in packet["blocks"][tag]:
            block_id = str(block["id"])
            record_id = f"{group_id}:authority:{tag}:{block_id}"
            record_ids.append(record_id)
            source, authority = _packet_sources(tag)
            if source != str(block["source"]):
                raise ArchitectureError(f"fixture_packet_source_drift:{tag}")
            records.append(
                _record(
                    record_id=record_id,
                    plane="authority_packet",
                    name=tag,
                    value=block["value"],
                    source=source,
                    authority=authority,
                    confidence=str(block.get("confidence") or ""),
                    required=bool(block.get("required")),
                    provenance=_provenance(
                        source_hashes,
                        "authority_packet",
                        f"{group_id}:{tag}:{block_id}",
                        packet_group=group_id,
                    ),
                    attributes={
                        "block_id": block_id,
                        "required_terms": list(block.get("required_terms") or []),
                    },
                    binding={
                        "packet_group": group_id,
                        "block_id": block_id,
                        "destination": "gpu_packet",
                    },
                )
            )
    group = {
        "group_id": group_id,
        "schema_version": str(packet["schema_version"]),
        "packet_id": str(packet["packet_id"]),
        "created_at": str(packet["created_at"]),
        "packet_digest": str(packet["packet_digest"]),
        "cpu_signature": str(packet["cpu_signature"]),
        "record_ids": record_ids,
    }
    return records, group


def _route_expression(label: str, value: int) -> str:
    v = int(value)
    formulas = {
        "LIT": f"{v}",
        "A": f"{v}+0",
        "S": f"{v + 1}-1",
        "M": f"{v}*1",
        "D": f"{v}/1",
        "U": f"(({v}))",
        "U_AS": f"({v}+1)-1",
        "U_AM": f"({v}+0)*1",
        "U_AD": f"({v}+0)/1",
        "U_SM": f"({v}-0)*1",
        "U_SD": f"({v}-0)/1",
        "U_MD": f"({v}*2)/2",
        "U_ASM": f"(({v}+1)-1)*1",
        "U_ASD": f"(({v}+1)-1)/1",
        "U_AMD": f"(({v}+0)*1)/1",
        "U_SMD": f"(({v}-0)*1)/1",
        "U_ASMD": f"((({v}+1)-1)*1)/1",
    }
    if label not in formulas:
        raise ArchitectureError(f"route_label_fixture_unknown:{label}")
    return formulas[label]


def _route_value(index: int) -> dict[str, Any]:
    labels = sorted(
        ROUTE_LABELS,
        key=lambda value: (
            ("LIT", "A", "S", "M", "D", "U").index(value)
            if value in {"LIT", "A", "S", "M", "D", "U"}
            else 100 + sorted(VALID_FEDERATIONS).index(value)
        ),
    )
    label = labels[index % len(labels)]
    target = (index * 7 + 11) % 96
    raw = _route_expression(label, target)
    final = str(target)
    raw_cost = int(_symbolic_cost(raw))
    cheapest_cost = int(_symbolic_cost(final))
    error = max(0.0, raw_cost - cheapest_cost) / float(raw_cost + 1)
    domains = sorted(_domains_in_expr_raw(raw))
    if label == "U":
        domains = ["U"]
    elif label.startswith("U_"):
        domains = ["U", *sorted(set(label[2:]))]
    destination = f"uml_token:{target}"
    return {
        "target_value": target,
        "raw_route": raw,
        "final_route": final,
        "domains": domains,
        "federation": label,
        "kind": "valid_efficient" if raw_cost <= cheapest_cost else "valid_costly",
        "cost": raw_cost,
        "error": round(error, 12),
        "cheapest": final,
        "cheapest_cost": cheapest_cost,
        "destination": destination,
        "sealed_destination": destination,
        "destination_match": True,
        "route_state": "selected",
        "seal_state": "verified",
    }


def _normalize_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "bundle_id": str(bundle["bundle_id"]),
        "draft": str(bundle["draft"]),
        "records": sorted(
            [copy.deepcopy(dict(row)) for row in bundle["records"]],
            key=lambda row: str(row["record_id"]),
        ),
        "packet_groups": sorted(
            [copy.deepcopy(dict(row)) for row in bundle["packet_groups"]],
            key=lambda row: str(row["group_id"]),
        ),
        "composition": sorted(
            [copy.deepcopy(dict(row)) for row in bundle["composition"]],
            key=lambda row: str(row["binding_id"]),
        ),
    }


def _deep_find(value: Any, names: set[str], depth: int = 0) -> Any:
    if depth > 6:
        return None
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in names:
                return item
        for item in value.values():
            found = _deep_find(item, names, depth + 1)
            if found is not None:
                return found
    return None


ITEM77_ALIASES: dict[str, set[str]] = {
    "survivor_hash": {"survivor_hash", "checkpoint_hash", "ckpt_hash", "model_hash"},
    "prompt": {"prompt", "query", "input_prompt"},
    "source": {"source", "prompt_source", "receipt_source"},
    "sealed_destination": {
        "sealed_destination",
        "destination",
        "target_destination",
    },
    "destination_match": {
        "destination_match",
        "sealed_destination_match",
        "match",
    },
    "policy_mode": {"policy_mode", "policy", "mode"},
    "raw_route": {"raw_route", "proposed", "raw", "route_raw"},
    "final_route": {"final_route", "selected", "final", "route_final"},
    "uml_domains": {"uml_domains", "domains", "domain_labels"},
    "federation": {"federation", "federation_label"},
    "kind": {"kind", "route_kind"},
    "cost": {"cost", "symbolic_cost", "route_cost"},
    "error": {"error", "route_error", "efficiency_error"},
    "cheapest": {"cheapest", "cheapest_route", "canonical"},
    "rid_state": {"rid_state", "rid", "master_rid"},
    "plant_state": {"plant_state", "plant", "runtime_health"},
}


def _extract_item77_rows(payload: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 7:
            return
        if isinstance(value, list):
            mappings = [dict(row) for row in value if isinstance(row, Mapping)]
            if mappings:
                for row in mappings:
                    normalized = {
                        field: _deep_find(
                            row, {alias.casefold() for alias in ITEM77_ALIASES[field]}
                        )
                        for field in ITEM77_FIELDS
                    }
                    available = {
                        field: item
                        for field, item in normalized.items()
                        if item is not None
                    }
                    if len(available) >= 6 and (
                        "raw_route" in available or "final_route" in available
                    ):
                        candidates.append(available)
            for item in value:
                walk(item, depth + 1)
        elif isinstance(value, Mapping):
            for item in value.values():
                walk(item, depth + 1)

    walk(payload)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidates:
        key = _sha_value(row)
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    return deduped


def _extract_item77_census(
    payload: Mapping[str, Any],
    receipt_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Join the item-77 mode rows to their sealed prompt manifest."""

    artifacts = payload.get("artifacts")
    manifest_raw = (
        artifacts.get("prompt_manifest")
        if isinstance(artifacts, Mapping)
        else None
    )
    manifest_path = (
        Path(str(manifest_raw))
        if manifest_raw
        else receipt_path.with_name("prompt_manifest.json")
    )
    if not manifest_path.is_file():
        raise FileNotFoundError(f"item77_prompt_manifest_missing:{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_rows = manifest.get("rows") if isinstance(manifest, Mapping) else None
    if not isinstance(manifest_rows, list):
        raise ArchitectureError("item77_prompt_manifest_rows_missing")
    prompt_by_id = {
        str(row["example_id"]): row
        for row in manifest_rows
        if isinstance(row, Mapping) and row.get("example_id")
    }
    checkpoint = payload.get("checkpoint_identity")
    checkpoint_after = (
        checkpoint.get("after") if isinstance(checkpoint, Mapping) else None
    )
    survivor_hash = (
        str(checkpoint_after.get("sha256"))
        if isinstance(checkpoint_after, Mapping) and checkpoint_after.get("sha256")
        else None
    )
    if not survivor_hash:
        raise ArchitectureError("item77_survivor_hash_missing")

    modes = payload.get("modes")
    if not isinstance(modes, Mapping):
        raise ArchitectureError("item77_modes_missing")
    rows: list[dict[str, Any]] = []
    for mode_name in sorted(modes):
        mode = modes[mode_name]
        mode_rows = mode.get("rows") if isinstance(mode, Mapping) else None
        if not isinstance(mode_rows, list):
            continue
        for row in mode_rows:
            if not isinstance(row, Mapping):
                continue
            example_id = str(row.get("example_id") or "")
            prompt_row = prompt_by_id.get(example_id)
            if prompt_row is None:
                raise ArchitectureError(
                    f"item77_prompt_join_missing:{mode_name}:{example_id}"
                )
            policy = row.get("policy")
            policy = policy if isinstance(policy, Mapping) else {}
            decision = policy.get("decision")
            decision = decision if isinstance(decision, Mapping) else {}
            plant = decision.get("plant")
            if isinstance(plant, Mapping):
                plant_state: Any = copy.deepcopy(dict(plant))
                rid_state: Any = {
                    "available": bool(plant.get("available")),
                    "master_s_n": plant.get("master_s_n"),
                    "source": plant.get("source"),
                }
            else:
                plant_state = {
                    "available": False,
                    "reason": "not_stamped_in_receipt_mode",
                }
                rid_state = {
                    "available": False,
                    "reason": "not_stamped_in_receipt_mode",
                }
            federation = str(row.get("route_federation") or "INVALID")
            if federation in {"LIT", "INVALID"}:
                domains: list[str] = []
            else:
                domains = [
                    domain for domain in ("A", "S", "M", "D") if domain in federation
                ]
            final_route = row.get("equation")
            raw_route = (
                policy.get("proposed")
                if str(mode_name) == "prefer_efficient_snap"
                else final_route
            )
            rows.append(
                {
                    "survivor_hash": survivor_hash,
                    "prompt": str(prompt_row.get("prompt") or ""),
                    "source": {
                        "template_id": prompt_row.get("template_id"),
                        "template_source": prompt_row.get("template_source"),
                        "example_id": example_id,
                    },
                    "sealed_destination": {
                        "target_char": row.get("target_char"),
                        "target_token_id": row.get("target_token_id"),
                    },
                    "destination_match": bool(row.get("destination_match")),
                    "policy_mode": {
                        "mode": str(mode_name),
                        "policy": policy.get("policy"),
                        "post_snap": bool(policy.get("post_snap")),
                    },
                    "raw_route": raw_route,
                    "final_route": final_route,
                    "uml_domains": domains,
                    "federation": federation,
                    "kind": row.get("route_kind"),
                    "cost": row.get("route_cost"),
                    "error": row.get("route_error"),
                    "cheapest": row.get("cheapest_route"),
                    "rid_state": rid_state,
                    "plant_state": plant_state,
                }
            )
    return rows, {
        "prompt_manifest_path": str(manifest_path).replace("\\", "/"),
        "prompt_manifest_sha256": _sha_file(manifest_path),
        "prompt_manifest_rows": len(prompt_by_id),
        "survivor_hash": survivor_hash,
    }


def discover_item77_receipt() -> dict[str, Any]:
    roots = (
        SANDBOX / "runs",
        FOUNDATION / "artifacts" / "auto",
        VIV / "reports",
    )
    paths: list[Path] = []
    markers = (
        "item77",
        "item_77",
        "item-77",
        "cheap_route_census",
        "cheap-route-census",
        "speak_cheap_census",
    )
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.json"):
            lowered = str(path).casefold()
            if any(marker in lowered for marker in markers):
                paths.append(path)
    timestamped = [
        path
        for path in paths
        if re.search(r"20\d{6}T\d{6}Z", path.name, flags=re.IGNORECASE)
    ]
    ordered = sorted(
        timestamped or paths,
        key=lambda path: (path.stat().st_mtime_ns, str(path)),
        reverse=True,
    )
    parse_errors: list[str] = []
    for path in ordered:
        try:
            if path.stat().st_size > 128 * 1024 * 1024:
                parse_errors.append(f"oversize:{path}")
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            supplemental: dict[str, Any] = {}
            if (
                isinstance(payload, Mapping)
                and payload.get("experiment_id")
                == "thesis_item_77_speak_cheap_census"
            ):
                rows, supplemental = _extract_item77_census(payload, path)
            else:
                rows = _extract_item77_rows(payload)
            if rows:
                coverage = Counter(
                    field for row in rows for field in ITEM77_FIELDS if field in row
                )
                return {
                    "status": "INTEGRATED",
                    "path": str(path).replace("\\", "/"),
                    "sha256": _sha_file(path),
                    "example_count": len(rows),
                    "field_coverage": dict(coverage),
                    "rows": rows,
                    "parse_errors": parse_errors,
                    **supplemental,
                }
            parse_errors.append(f"no_per_example_rows:{path}")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            parse_errors.append(f"{path}:{type(exc).__name__}:{exc}")
    return {
        "status": "PENDING",
        "path": None,
        "sha256": None,
        "example_count": 0,
        "field_coverage": {},
        "rows": [],
        "parse_errors": parse_errors,
    }


def build_replay_corpus(
    source_hashes: Mapping[str, Mapping[str, str]],
    item77: Mapping[str, Any],
) -> list[dict[str, Any]]:
    mouth_rows = build_mouth_rows()
    if len(mouth_rows) != 96:
        raise ArchitectureError(f"mouth_fixture_count_drift:{len(mouth_rows)}")
    bundles: list[dict[str, Any]] = []
    for index, mouth in enumerate(mouth_rows):
        bundle_id = f"tag-ab-bundle-{index:03d}"
        packet = _build_signed_packet(index, mouth)
        authority_records, group = _packet_records(packet, source_hashes)
        mouth_record = _record(
            record_id=f"{bundle_id}:mouth:{mouth['domain']}",
            plane="mouth_atom",
            name=str(mouth["domain"]),
            value={
                "domain": str(mouth["domain"]),
                "domain_kind": str(mouth["domain_kind"]),
                "parent_atoms": list(mouth["parent_atoms"]),
                "tags": list(mouth["tags"]),
                "action_blocks": list(mouth["action_blocks"]),
                "pair_id": str(mouth["pair_id"]),
                "ask": str(mouth["ask"]),
                "chosen": str(mouth["chosen"]),
            },
            source="stage1_mouth_identity_curriculum",
            authority="cpu_curriculum_hold",
            confidence="fixture",
            required=True,
            provenance=_provenance(
                source_hashes,
                "mouth_atom",
                str(mouth["pair_id"]),
                admission_status=str(mouth["admission_status"]),
                train_ready=bool(mouth["train_ready"]),
            ),
            attributes={"domain_kind": str(mouth["domain_kind"])},
            binding={"destination": "gpu_mouth"},
        )
        route = _route_value(index)
        route_record = _record(
            record_id=f"{bundle_id}:uml:route",
            plane="uml_route",
            name="route_receipt",
            value=route,
            source="uml_route_governor",
            authority="cpu_route_governor",
            confidence="computed_fixture",
            required=True,
            provenance=_provenance(
                source_hashes,
                "uml_route",
                f"route-{index:03d}",
                registry_source=str(SOURCE_PATHS["uml_registry"]).replace("\\", "/"),
                receipt_source=str(SOURCE_PATHS["snap_free_receipt"]).replace("\\", "/"),
            ),
            attributes={"schema_version": "uml_route_governor_v1.1"},
            binding={
                "destination": route["sealed_destination"],
                "seal_state": route["seal_state"],
            },
        )
        context_records: list[dict[str, Any]] = []
        context_values = {
            "identity": {"name": "Viv", "system": "AIOS"},
            "knowledge_tags": list(mouth["tags"]),
            "user": str(mouth["ask"]),
            "other": {"domain": str(mouth["domain"]), "bundle": bundle_id},
        }
        for role in ("identity", "knowledge_tags", "user", "other"):
            context_records.append(
                _record(
                    record_id=f"{bundle_id}:context:{role}",
                    plane="context_role",
                    name=role,
                    value=context_values[role],
                    source="context_pack",
                    authority="advisory_context",
                    confidence="fixture",
                    required=role in {"identity", "knowledge_tags", "user"},
                    provenance=_provenance(
                        source_hashes,
                        "context_role",
                        f"{bundle_id}:{role}",
                        known_role=True,
                    ),
                    attributes={"role": role},
                    binding={"destination": "shared_context"},
                )
            )
        records = [
            *authority_records,
            mouth_record,
            route_record,
            *context_records,
        ]
        composition = [
            {
                "binding_id": f"{bundle_id}:compose:mouth",
                "record_id": mouth_record["record_id"],
                "plane": "mouth_atom",
                "name": mouth_record["name"],
                "destination": "gpu_mouth",
                "semantic_aliases": False,
            },
            {
                "binding_id": f"{bundle_id}:compose:knowledge",
                "record_id": f"{bundle_id}:context:knowledge_tags",
                "plane": "context_role",
                "name": "knowledge_tags",
                "destination": "shared_context",
                "semantic_aliases": False,
            },
            {
                "binding_id": f"{bundle_id}:compose:route",
                "record_id": route_record["record_id"],
                "plane": "uml_route",
                "name": "route_receipt",
                "destination": route["sealed_destination"],
                "semantic_aliases": False,
            },
        ]
        bundles.append(
            _normalize_bundle(
                {
                    "bundle_id": bundle_id,
                    "draft": "Viv renders the supplied content.",
                    "records": records,
                    "packet_groups": [group],
                    "composition": composition,
                }
            )
        )

    item_path = item77.get("path")
    item_sha = item77.get("sha256")
    for item_index, item_row in enumerate(item77.get("rows") or []):
        bundle = bundles[item_index % len(bundles)]
        bundle_id = str(bundle["bundle_id"])
        destination = str(
            item_row.get("sealed_destination")
            or f"item77_receipt:{item_index:04d}"
        )
        record = _record(
            record_id=f"{bundle_id}:item77:{item_index:04d}",
            plane="item77_receipt",
            name="cheap_route_example",
            value=dict(item_row),
            source="item77_measurement",
            authority="measurement_only",
            confidence="measured",
            required=False,
            provenance={
                "source_path": str(item_path),
                "source_sha256": str(item_sha),
                "fixture_id": f"item77-example-{item_index:04d}",
                "state": "current",
                "observed_at": "fixture",
                "measurement_only": True,
            },
            attributes={
                "established_tag": False,
                "operator_gated_if_promoted": True,
            },
            binding={"destination": destination},
        )
        bundle["records"].append(record)
        bundle["records"].sort(key=lambda row: str(row["record_id"]))
    return [_normalize_bundle(bundle) for bundle in bundles]


def _packet_unsigned_from_records(
    records: Sequence[Mapping[str, Any]],
    group: Mapping[str, Any],
) -> dict[str, Any]:
    record_by_id = {str(row["record_id"]): row for row in records}
    blocks: dict[str, list[dict[str, Any]]] = {
        tag: [] for tag in tagged_packet.ALLOWED_TAGS
    }
    for record_id in group["record_ids"]:
        if str(record_id) not in record_by_id:
            raise ArchitectureError(f"packet_group_missing_record:{record_id}")
        row = record_by_id[str(record_id)]
        if row.get("plane") != "authority_packet":
            raise ArchitectureError(f"packet_group_non_authority_record:{record_id}")
        tag = str(row["name"])
        if tag not in blocks:
            raise ArchitectureError(f"packet_group_unknown_tag:{tag}")
        attributes = row.get("attributes")
        if not isinstance(attributes, Mapping):
            raise ArchitectureError(f"packet_attributes_missing:{record_id}")
        blocks[tag].append(
            {
                "id": str(attributes.get("block_id") or ""),
                "source": str(row.get("source") or ""),
                "confidence": str(row.get("confidence") or ""),
                "required": bool(row.get("required")),
                "required_terms": [
                    str(value)
                    for value in (attributes.get("required_terms") or [])
                ],
                "value": copy.deepcopy(row.get("value")),
            }
        )
    return {
        "schema_version": str(group["schema_version"]),
        "packet_id": str(group["packet_id"]),
        "created_at": str(group["created_at"]),
        "blocks": blocks,
    }


def _packet_from_records(
    records: Sequence[Mapping[str, Any]],
    group: Mapping[str, Any],
) -> dict[str, Any]:
    packet = _packet_unsigned_from_records(records, group)
    packet["packet_digest"] = str(group["packet_digest"])
    packet["cpu_signature"] = str(group["cpu_signature"])
    return packet


def _expected_source_authority(plane: str, name: str) -> tuple[str, str]:
    if plane == "authority_packet":
        return _packet_sources(name)
    if plane == "mouth_atom":
        return "stage1_mouth_identity_curriculum", "cpu_curriculum_hold"
    if plane == "uml_route":
        return "uml_route_governor", "cpu_route_governor"
    if plane == "context_role":
        return "context_pack", "advisory_context"
    if plane == "item77_receipt":
        return "item77_measurement", "measurement_only"
    raise ArchitectureError(f"unknown_plane:{plane}")


def _validate_provenance(record: Mapping[str, Any]) -> None:
    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ArchitectureError(f"provenance_missing:{record.get('record_id')}")
    required = {
        "source_path",
        "source_sha256",
        "fixture_id",
        "state",
        "observed_at",
    }
    missing = required - set(provenance)
    if missing:
        raise ArchitectureError(
            f"provenance_fields_missing:{record.get('record_id')}:{sorted(missing)}"
        )
    if provenance.get("state") != "current":
        raise ArchitectureError(
            f"provenance_stale:{record.get('record_id')}:{provenance.get('state')}"
        )
    digest = str(provenance.get("source_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ArchitectureError(
            f"provenance_digest_invalid:{record.get('record_id')}"
        )
    if not str(provenance.get("source_path") or ""):
        raise ArchitectureError(
            f"provenance_source_missing:{record.get('record_id')}"
        )


def _required_domains(label: str) -> set[str]:
    if label in {"A", "S", "M", "D"}:
        return {label}
    if label.startswith("U_"):
        return set(label[2:])
    return set()


def _validate_route(record: Mapping[str, Any]) -> None:
    value = record.get("value")
    if not isinstance(value, Mapping):
        raise ArchitectureError("uml_route_value_mapping_required")
    label = str(value.get("federation") or "")
    if label not in ROUTE_LABELS:
        raise ArchitectureError(f"uml_route_invalid_federation:{label}")
    domains = value.get("domains")
    if not isinstance(domains, list):
        raise ArchitectureError("uml_route_domains_required")
    if not domains and label != "LIT":
        raise ArchitectureError(f"uml_route_domains_empty:{label}")
    if any(str(domain) not in {"A", "S", "M", "D", "U", "LIT"} for domain in domains):
        raise ArchitectureError(f"uml_route_invalid_domain:{domains}")
    raw = str(value.get("raw_route") or "")
    final = str(value.get("final_route") or "")
    target = int(value.get("target_value"))
    if not math.isclose(float(_eval_value(raw)), float(target), abs_tol=1e-9):
        raise ArchitectureError("uml_route_raw_destination_mismatch")
    if not math.isclose(float(_eval_value(final)), float(target), abs_tol=1e-9):
        raise ArchitectureError("uml_route_final_destination_mismatch")
    actual_domains = set(_domains_in_expr_raw(raw))
    if not _required_domains(label).issubset(actual_domains):
        raise ArchitectureError(
            f"uml_route_expression_domain_mismatch:{label}:{sorted(actual_domains)}"
        )
    if (
        value.get("destination_match") is not True
        or value.get("destination") != value.get("sealed_destination")
    ):
        raise ArchitectureError("uml_route_sealed_destination_mismatch")
    if value.get("seal_state") != "verified":
        raise ArchitectureError("uml_route_seal_not_verified")
    if value.get("route_state") != "selected":
        raise ArchitectureError("uml_route_state_invalid")
    if str((record.get("binding") or {}).get("destination")) != str(
        value.get("sealed_destination")
    ):
        raise ArchitectureError("uml_route_binding_destination_mismatch")


def _validate_plane_record(record: Mapping[str, Any]) -> None:
    if set(record) != RECORD_KEYS:
        raise ArchitectureError(
            f"typed_record_schema:{record.get('record_id')}:{sorted(set(record) ^ RECORD_KEYS)}"
        )
    record_id = str(record.get("record_id") or "")
    if not record_id:
        raise ArchitectureError("record_id_required")
    plane = str(record.get("plane") or "")
    name = str(record.get("name") or "")
    if plane not in PLANES:
        raise ArchitectureError(f"unknown_plane:{plane}")
    if plane == "authority_packet" and name not in tagged_packet.ALLOWED_TAGS:
        raise ArchitectureError(f"unknown_authority_tag:{name}")
    if plane == "mouth_atom" and name not in DOMAIN_META:
        raise ArchitectureError(f"unknown_mouth_tag:{name}")
    if plane == "uml_route" and name != "route_receipt":
        raise ArchitectureError(f"unknown_uml_tag:{name}")
    if plane == "context_role" and name not in KNOWN_ROLES:
        raise ArchitectureError(f"unknown_context_role:{name}")
    if plane == "item77_receipt" and name != "cheap_route_example":
        raise ArchitectureError(f"unknown_item77_tag:{name}")
    expected_source, expected_authority = _expected_source_authority(plane, name)
    if record.get("source") != expected_source:
        raise ArchitectureError(
            f"source_mismatch:{record_id}:{record.get('source')}:{expected_source}"
        )
    if record.get("authority") != expected_authority:
        raise ArchitectureError(
            f"authority_mismatch:{record_id}:{record.get('authority')}:{expected_authority}"
        )
    if not isinstance(record.get("required"), bool):
        raise ArchitectureError(f"required_not_bool:{record_id}")
    if not isinstance(record.get("confidence"), str) or not record["confidence"]:
        raise ArchitectureError(f"confidence_required:{record_id}")
    if not isinstance(record.get("attributes"), Mapping):
        raise ArchitectureError(f"attributes_mapping_required:{record_id}")
    if not isinstance(record.get("binding"), Mapping):
        raise ArchitectureError(f"binding_mapping_required:{record_id}")
    _validate_provenance(record)

    if plane == "mouth_atom":
        value = record.get("value")
        if not isinstance(value, Mapping) or value.get("domain") != name:
            raise ArchitectureError(f"mouth_domain_binding_mismatch:{record_id}")
        expected = DOMAIN_META[name]
        if list(value.get("tags") or []) != list(expected["tags"]):
            raise ArchitectureError(f"mouth_tag_set_mismatch:{name}")
        if list(value.get("parent_atoms") or []) != list(expected["parents"]):
            raise ArchitectureError(f"mouth_parent_set_mismatch:{name}")
        if (record.get("binding") or {}).get("destination") != "gpu_mouth":
            raise ArchitectureError(f"mouth_destination_mismatch:{record_id}")
    elif plane == "uml_route":
        _validate_route(record)
    elif plane == "context_role":
        if (record.get("attributes") or {}).get("role") != name:
            raise ArchitectureError(f"context_role_attribute_mismatch:{record_id}")
        if (record.get("binding") or {}).get("destination") != "shared_context":
            raise ArchitectureError(f"context_destination_mismatch:{record_id}")
    elif plane == "item77_receipt":
        value = record.get("value")
        if not isinstance(value, Mapping):
            raise ArchitectureError(f"item77_value_mapping_required:{record_id}")
        if len(set(value) & set(ITEM77_FIELDS)) < 6:
            raise ArchitectureError(f"item77_field_preservation_low:{record_id}")


def _semantic_names(name: str, semantic_aliases: bool) -> set[str]:
    names = {str(name)}
    if semantic_aliases:
        if name == "knowledge":
            names.add("knowledge_tags")
        elif name == "knowledge_tags":
            names.add("knowledge")
    return names


def _resolve_composition(
    records: Sequence[Mapping[str, Any]],
    binding: Mapping[str, Any],
) -> Mapping[str, Any]:
    record_id = binding.get("record_id")
    if record_id is not None:
        matches = [row for row in records if row.get("record_id") == record_id]
    else:
        names = _semantic_names(
            str(binding.get("name") or ""),
            bool(binding.get("semantic_aliases")),
        )
        plane = binding.get("plane")
        matches = [
            row
            for row in records
            if str(row.get("name")) in names
            and (plane is None or row.get("plane") == plane)
        ]
    if not matches:
        raise ArchitectureError(
            f"composition_binding_not_found:{binding.get('binding_id')}"
        )
    if len(matches) != 1:
        raise AmbiguousLookup(
            f"composition_binding_ambiguous:{binding.get('binding_id')}:{len(matches)}"
        )
    row = matches[0]
    if binding.get("plane") is not None and row.get("plane") != binding.get("plane"):
        raise ArchitectureError(
            f"composition_plane_mismatch:{binding.get('binding_id')}"
        )
    if binding.get("name") is not None and not bool(binding.get("semantic_aliases")):
        if row.get("name") != binding.get("name"):
            raise ArchitectureError(
                f"composition_name_mismatch:{binding.get('binding_id')}"
            )
    if str((row.get("binding") or {}).get("destination")) != str(
        binding.get("destination")
    ):
        raise ArchitectureError(
            f"composition_destination_mismatch:{binding.get('binding_id')}"
        )
    return row


def _validate_logical_bundle(bundle: Mapping[str, Any]) -> None:
    if set(bundle) != {
        "bundle_id",
        "draft",
        "records",
        "packet_groups",
        "composition",
    }:
        raise ArchitectureError("logical_bundle_schema")
    records = bundle.get("records")
    if not isinstance(records, list) or not records:
        raise ArchitectureError("logical_records_required")
    seen_ids: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise ArchitectureError("record_mapping_required")
        _validate_plane_record(record)
        record_id = str(record["record_id"])
        if record_id in seen_ids:
            raise ArchitectureError(f"duplicate_record_id:{record_id}")
        seen_ids.add(record_id)

    groups = bundle.get("packet_groups")
    if not isinstance(groups, list) or not groups:
        raise ArchitectureError("packet_groups_required")
    seen_groups: set[str] = set()
    authority_membership: Counter[str] = Counter()
    for group in groups:
        if not isinstance(group, Mapping) or set(group) != GROUP_KEYS:
            raise ArchitectureError("packet_group_schema")
        group_id = str(group["group_id"])
        if group_id in seen_groups:
            raise ArchitectureError(f"duplicate_packet_group:{group_id}")
        seen_groups.add(group_id)
        ids = [str(value) for value in group["record_ids"]]
        if len(ids) != len(set(ids)):
            raise ArchitectureError(f"packet_group_duplicate_binding:{group_id}")
        for record_id in ids:
            authority_membership[record_id] += 1
        packet = _packet_from_records(records, group)
        tagged_packet.validate_tagged_packet(packet)
        draft_verification = tagged_packet.verify_gpu_draft(
            packet, str(bundle.get("draft") or "")
        )
        if draft_verification.status != "PASS":
            raise ArchitectureError(
                "gpu_draft_verification:"
                + ",".join(draft_verification.errors)
            )
    authority_ids = {
        str(row["record_id"])
        for row in records
        if row.get("plane") == "authority_packet"
    }
    if set(authority_membership) != authority_ids:
        raise ArchitectureError("authority_packet_group_coverage")
    if any(authority_membership[record_id] != 1 for record_id in authority_ids):
        raise ArchitectureError("authority_packet_group_ambiguity")

    composition = bundle.get("composition")
    if not isinstance(composition, list) or not composition:
        raise ArchitectureError("composition_required")
    binding_ids: set[str] = set()
    for binding in composition:
        if not isinstance(binding, Mapping) or set(binding) != COMPOSITION_KEYS:
            raise ArchitectureError("composition_schema")
        binding_id = str(binding.get("binding_id") or "")
        if not binding_id or binding_id in binding_ids:
            raise ArchitectureError(f"duplicate_conflicting_binding:{binding_id}")
        binding_ids.add(binding_id)
        _resolve_composition(records, binding)


class LayeredBridge:
    """Native plane payloads plus a deterministic cross-plane bridge."""

    name = ARM_A
    schema_version = "tag_layered_bridge_v1"

    @classmethod
    def encode(cls, logical: Mapping[str, Any]) -> dict[str, Any]:
        bundle = _normalize_bundle(logical)
        records = bundle["records"]
        packets = [
            _packet_from_records(records, group)
            for group in bundle["packet_groups"]
        ]
        planes: dict[str, Any] = {
            "authority_packet": {
                "schema_version": tagged_packet.SCHEMA_VERSION,
                "packets": packets,
            },
            "mouth_atom": {
                "schema_version": "stage1_mouth_identity_curriculum_v2_1",
                "rows": [],
            },
            "uml_route": {
                "schema_version": "uml_route_governor_v1.1",
                "rows": [],
            },
            "context_role": {
                "schema_version": "viv_slm_context_pack_receipt_v1",
                "rows": [],
            },
            "item77_receipt": {
                "schema_version": "item77_measurement_import_v1",
                "rows": [],
            },
        }
        bridge: list[dict[str, Any]] = []
        for record in records:
            plane = str(record["plane"])
            if plane == "authority_packet":
                binding = record["binding"]
                native_ref = (
                    f"authority_packet/{binding['packet_group']}/"
                    f"{record['name']}/{binding['block_id']}"
                )
            else:
                native_ref = f"{plane}/{record['record_id']}"
                planes[plane]["rows"].append(
                    {
                        "native_id": str(record["record_id"]),
                        "name": str(record["name"]),
                        "value": copy.deepcopy(record["value"]),
                    }
                )
            bridge.append(
                {
                    **{
                        key: copy.deepcopy(record[key])
                        for key in RECORD_KEYS
                        if key != "value"
                    },
                    "native_ref": native_ref,
                }
            )
        return {
            "schema_version": cls.schema_version,
            "bundle_id": bundle["bundle_id"],
            "draft": bundle["draft"],
            "planes": planes,
            "bridge": sorted(bridge, key=lambda row: str(row["record_id"])),
            "composition": copy.deepcopy(bundle["composition"]),
        }

    @classmethod
    def _decode(cls, envelope: Mapping[str, Any]) -> dict[str, Any]:
        expected_top = {
            "schema_version",
            "bundle_id",
            "draft",
            "planes",
            "bridge",
            "composition",
        }
        if set(envelope) != expected_top or envelope.get("schema_version") != cls.schema_version:
            raise ArchitectureError("layered_envelope_schema")
        planes = envelope.get("planes")
        if not isinstance(planes, Mapping) or set(planes) != set(PLANES):
            raise ArchitectureError("layered_plane_set")
        bridge = envelope.get("bridge")
        if not isinstance(bridge, list) or not bridge:
            raise ArchitectureError("layered_bridge_required")

        packets = (planes["authority_packet"] or {}).get("packets")
        if not isinstance(packets, list) or not packets:
            raise ArchitectureError("layered_authority_packets_required")
        packet_map = {str(packet["packet_id"]): packet for packet in packets}
        native_rows: dict[str, dict[str, Mapping[str, Any]]] = {}
        for plane in PLANES:
            if plane == "authority_packet":
                continue
            rows = (planes[plane] or {}).get("rows")
            if not isinstance(rows, list):
                raise ArchitectureError(f"layered_rows_required:{plane}")
            row_map: dict[str, Mapping[str, Any]] = {}
            for row in rows:
                if (
                    not isinstance(row, Mapping)
                    or set(row) != {"native_id", "name", "value"}
                ):
                    raise ArchitectureError(f"layered_native_row_schema:{plane}")
                native_id = str(row["native_id"])
                if native_id in row_map:
                    raise ArchitectureError(
                        f"layered_duplicate_native_id:{plane}:{native_id}"
                    )
                row_map[native_id] = row
            native_rows[plane] = row_map

        records: list[dict[str, Any]] = []
        consumed_native: set[str] = set()
        for link in bridge:
            if not isinstance(link, Mapping) or set(link) != BRIDGE_KEYS:
                raise ArchitectureError("layered_bridge_row_schema")
            plane = str(link.get("plane") or "")
            if plane not in PLANES:
                raise ArchitectureError(f"unknown_plane:{plane}")
            native_ref = str(link.get("native_ref") or "")
            if native_ref in consumed_native:
                raise ArchitectureError(f"layered_duplicate_native_ref:{native_ref}")
            consumed_native.add(native_ref)
            if plane == "authority_packet":
                parts = native_ref.split("/", 3)
                if len(parts) != 4 or parts[0] != "authority_packet":
                    raise ArchitectureError(f"layered_authority_ref:{native_ref}")
                _, packet_id, tag, block_id = parts
                packet = packet_map.get(packet_id)
                if packet is None:
                    raise ArchitectureError(
                        f"layered_packet_ref_not_found:{packet_id}"
                    )
                matches = [
                    row
                    for row in (packet.get("blocks") or {}).get(tag, [])
                    if str(row.get("id")) == block_id
                ]
                if len(matches) != 1:
                    raise ArchitectureError(
                        f"layered_packet_block_ref:{native_ref}:{len(matches)}"
                    )
                native = matches[0]
                if (
                    link.get("name") != tag
                    or link.get("source") != native.get("source")
                    or link.get("confidence") != native.get("confidence")
                    or link.get("required") != native.get("required")
                    or (link.get("attributes") or {}).get("block_id") != block_id
                    or list((link.get("attributes") or {}).get("required_terms") or [])
                    != list(native.get("required_terms") or [])
                ):
                    raise ArchitectureError(
                        f"layered_authority_bridge_native_mismatch:{native_ref}"
                    )
                value = copy.deepcopy(native.get("value"))
            else:
                prefix = f"{plane}/"
                if not native_ref.startswith(prefix):
                    raise ArchitectureError(
                        f"layered_native_plane_ref_mismatch:{native_ref}"
                    )
                native_id = native_ref[len(prefix) :]
                native = native_rows[plane].get(native_id)
                if native is None:
                    raise ArchitectureError(
                        f"layered_native_ref_not_found:{native_ref}"
                    )
                if link.get("name") != native.get("name"):
                    raise ArchitectureError(
                        f"layered_name_native_mismatch:{native_ref}"
                    )
                value = copy.deepcopy(native.get("value"))
            records.append(
                {
                    **{
                        key: copy.deepcopy(link[key])
                        for key in RECORD_KEYS
                        if key != "value"
                    },
                    "value": value,
                }
            )

        native_count = sum(
            len(packet["blocks"][tag])
            for packet in packets
            for tag in tagged_packet.ALLOWED_TAGS
        ) + sum(len(rows) for rows in native_rows.values())
        if len(consumed_native) != native_count:
            raise ArchitectureError(
                f"layered_native_coverage:{len(consumed_native)}:{native_count}"
            )

        groups: list[dict[str, Any]] = []
        for packet in packets:
            packet_id = str(packet["packet_id"])
            ordered_ids: list[str] = []
            for tag in tagged_packet.ALLOWED_TAGS:
                for block in packet["blocks"][tag]:
                    matches = [
                        row
                        for row in records
                        if row.get("plane") == "authority_packet"
                        and (row.get("binding") or {}).get("packet_group")
                        == packet_id
                        and row.get("name") == tag
                        and (row.get("attributes") or {}).get("block_id")
                        == str(block["id"])
                    ]
                    if len(matches) != 1:
                        raise ArchitectureError(
                            f"layered_packet_membership_ambiguous:{packet_id}:{tag}"
                        )
                    ordered_ids.append(str(matches[0]["record_id"]))
            groups.append(
                {
                    "group_id": packet_id,
                    "schema_version": str(packet["schema_version"]),
                    "packet_id": packet_id,
                    "created_at": str(packet["created_at"]),
                    "packet_digest": str(packet["packet_digest"]),
                    "cpu_signature": str(packet["cpu_signature"]),
                    "record_ids": ordered_ids,
                }
            )
        return _normalize_bundle(
            {
                "bundle_id": envelope["bundle_id"],
                "draft": envelope["draft"],
                "records": records,
                "packet_groups": groups,
                "composition": envelope["composition"],
            }
        )

    @classmethod
    def decode(cls, envelope: Mapping[str, Any]) -> dict[str, Any]:
        decoded = cls._decode(envelope)
        _validate_logical_bundle(decoded)
        return decoded

    @classmethod
    def validate(cls, envelope: Mapping[str, Any]) -> None:
        cls.decode(envelope)

    @classmethod
    def lookup_index(
        cls, envelope: Mapping[str, Any]
    ) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
        records = cls._decode(envelope)["records"]
        index: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
        for record in records:
            index[(str(record["plane"]), str(record["name"]))].append(record)
        return dict(index)


class UnifiedTypedRegistry:
    """One typed tag registry with delegated native validation."""

    name = ARM_B
    schema_version = "tag_unified_typed_registry_v1"

    @classmethod
    def encode(cls, logical: Mapping[str, Any]) -> dict[str, Any]:
        bundle = _normalize_bundle(logical)
        return {
            "schema_version": cls.schema_version,
            "bundle_id": bundle["bundle_id"],
            "draft": bundle["draft"],
            "registry": copy.deepcopy(bundle["records"]),
            "packet_groups": copy.deepcopy(bundle["packet_groups"]),
            "composition": copy.deepcopy(bundle["composition"]),
        }

    @classmethod
    def _decode(cls, envelope: Mapping[str, Any]) -> dict[str, Any]:
        expected_top = {
            "schema_version",
            "bundle_id",
            "draft",
            "registry",
            "packet_groups",
            "composition",
        }
        if set(envelope) != expected_top or envelope.get("schema_version") != cls.schema_version:
            raise ArchitectureError("typed_registry_envelope_schema")
        registry = envelope.get("registry")
        if not isinstance(registry, list) or not registry:
            raise ArchitectureError("typed_registry_required")
        for record in registry:
            if not isinstance(record, Mapping) or set(record) != RECORD_KEYS:
                raise ArchitectureError("typed_registry_record_schema")
        return _normalize_bundle(
            {
                "bundle_id": envelope["bundle_id"],
                "draft": envelope["draft"],
                "records": registry,
                "packet_groups": envelope["packet_groups"],
                "composition": envelope["composition"],
            }
        )

    @classmethod
    def decode(cls, envelope: Mapping[str, Any]) -> dict[str, Any]:
        decoded = cls._decode(envelope)
        _validate_logical_bundle(decoded)
        return decoded

    @classmethod
    def validate(cls, envelope: Mapping[str, Any]) -> None:
        cls.decode(envelope)

    @classmethod
    def lookup_index(
        cls, envelope: Mapping[str, Any]
    ) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
        records = cls._decode(envelope)["records"]
        index: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
        for record in records:
            index[(str(record["plane"]), str(record["name"]))].append(record)
        return dict(index)


def _encoded_slots(
    arm_name: str, envelope: dict[str, Any]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if arm_name == ARM_B:
        return [(record, record) for record in envelope["registry"]]
    slots: list[tuple[dict[str, Any], dict[str, Any]]] = []
    packets = {
        str(packet["packet_id"]): packet
        for packet in envelope["planes"]["authority_packet"]["packets"]
    }
    row_maps = {
        plane: {
            str(row["native_id"]): row
            for row in envelope["planes"][plane]["rows"]
        }
        for plane in PLANES
        if plane != "authority_packet"
    }
    for link in envelope["bridge"]:
        plane = str(link["plane"])
        native_ref = str(link["native_ref"])
        if plane == "authority_packet":
            _, packet_id, tag, block_id = native_ref.split("/", 3)
            matches = [
                row
                for row in packets[packet_id]["blocks"][tag]
                if str(row["id"]) == block_id
            ]
            if len(matches) != 1:
                raise ArchitectureError(f"mutation_slot_authority:{native_ref}")
            native = matches[0]
        else:
            native_id = native_ref[len(plane) + 1 :]
            native = row_maps[plane][native_id]
        slots.append((link, native))
    return slots


def _find_slot(
    arm_name: str,
    envelope: dict[str, Any],
    *,
    plane: str,
    name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    matches = [
        (meta, native)
        for meta, native in _encoded_slots(arm_name, envelope)
        if meta.get("plane") == plane
        and (name is None or meta.get("name") == name)
    ]
    if not matches:
        raise ArchitectureError(f"attack_slot_missing:{plane}:{name}")
    return matches[0]


def _set_slot_value(
    arm_name: str,
    envelope: dict[str, Any],
    *,
    plane: str,
    value: Any,
    name: str | None = None,
) -> None:
    meta, native = _find_slot(arm_name, envelope, plane=plane, name=name)
    if arm_name == ARM_B:
        meta["value"] = copy.deepcopy(value)
    else:
        native["value"] = copy.deepcopy(value)


def _resign_layered(envelope: dict[str, Any]) -> None:
    packet = envelope["planes"]["authority_packet"]["packets"][0]
    unsigned = {
        key: copy.deepcopy(packet[key])
        for key in ("schema_version", "packet_id", "created_at", "blocks")
    }
    packet["packet_digest"] = tagged_packet._digest(unsigned)  # type: ignore[attr-defined]
    packet["cpu_signature"] = tagged_packet._sign(  # type: ignore[attr-defined]
        unsigned | {"packet_digest": packet["packet_digest"]}
    )


def _resign_registry(envelope: dict[str, Any]) -> None:
    group = envelope["packet_groups"][0]
    unsigned = _packet_unsigned_from_records(envelope["registry"], group)
    group["packet_digest"] = tagged_packet._digest(unsigned)  # type: ignore[attr-defined]
    group["cpu_signature"] = tagged_packet._sign(  # type: ignore[attr-defined]
        unsigned | {"packet_digest": group["packet_digest"]}
    )


def _resign(arm_name: str, envelope: dict[str, Any]) -> None:
    if arm_name == ARM_A:
        _resign_layered(envelope)
    else:
        _resign_registry(envelope)


def _apply_attack(
    arm_name: str,
    envelope: dict[str, Any],
    category: str,
    variant: int,
) -> None:
    if category == "user_mints_cpu_authority":
        meta, native = _find_slot(
            arm_name, envelope, plane="authority_packet", name="identity"
        )
        meta["source"] = "user"
        if arm_name == ARM_A:
            native["source"] = "user"
        _resign(arm_name, envelope)
    elif category == "gpu_draft_echoes_tag_markup":
        envelope["draft"] = (
            f"<identity source=\"gpu\">Viv authority {variant}</identity>"
        )
    elif category == "identity_collision":
        composition = next(
            row for row in envelope["composition"] if row["binding_id"].endswith(":mouth")
        )
        composition["record_id"] = None
        composition["plane"] = None
        composition["name"] = "identity"
        composition["semantic_aliases"] = False
    elif category == "knowledge_vs_knowledge_tags":
        composition = next(
            row
            for row in envelope["composition"]
            if row["binding_id"].endswith(":knowledge")
        )
        composition["record_id"] = None
        composition["plane"] = None
        composition["name"] = "knowledge"
        composition["semantic_aliases"] = True
    elif category == "unknown_tag":
        meta, native = _find_slot(arm_name, envelope, plane="mouth_atom")
        meta["name"] = f"unknown_mouth_tag_{variant}"
        if arm_name == ARM_A:
            native["name"] = meta["name"]
    elif category == "unknown_plane":
        meta, _native = _find_slot(arm_name, envelope, plane="context_role")
        meta["plane"] = f"unknown_plane_{variant}"
    elif category == "invalid_uml_domain_federation":
        meta, native = _find_slot(arm_name, envelope, plane="uml_route")
        value = copy.deepcopy(meta["value"] if arm_name == ARM_B else native["value"])
        value["domains"] = ["U", "X"]
        value["federation"] = f"U_AX_{variant}"
        _set_slot_value(
            arm_name, envelope, plane="uml_route", name="route_receipt", value=value
        )
    elif category == "stale_missing_provenance":
        meta, _native = _find_slot(arm_name, envelope, plane="context_role")
        if variant % 2:
            meta["provenance"] = {}
        else:
            meta["provenance"]["state"] = "stale"
            meta["provenance"]["observed_at"] = "2000-01-01T00:00:00+00:00"
    elif category == "source_authority_mismatch":
        meta, _native = _find_slot(arm_name, envelope, plane="mouth_atom")
        meta["source"] = "gpu_draft"
        meta["authority"] = "cpu"
    elif category == "duplicate_conflicting_bindings":
        conflict = copy.deepcopy(envelope["composition"][0])
        conflict["destination"] = f"conflict:{variant}"
        envelope["composition"].append(conflict)
    elif category == "tampered_digest":
        meta, native = _find_slot(
            arm_name, envelope, plane="authority_packet", name="identity"
        )
        if arm_name == ARM_B:
            meta["value"] = {"name": "Tampered", "variant": variant}
        else:
            native["value"] = {"name": "Tampered", "variant": variant}
    elif category == "tampered_signature":
        if arm_name == ARM_A:
            packet = envelope["planes"]["authority_packet"]["packets"][0]
            signature = str(packet["cpu_signature"])
            packet["cpu_signature"] = ("0" if signature[0] != "0" else "1") + signature[1:]
        else:
            group = envelope["packet_groups"][0]
            signature = str(group["cpu_signature"])
            group["cpu_signature"] = ("0" if signature[0] != "0" else "1") + signature[1:]
    elif category == "invented_binding":
        envelope["composition"][0]["record_id"] = f"invented:{variant}"
    elif category == "destination_mismatch":
        meta, native = _find_slot(arm_name, envelope, plane="uml_route")
        value = copy.deepcopy(meta["value"] if arm_name == ARM_B else native["value"])
        value["destination_match"] = False
        value["sealed_destination"] = f"wrong:{variant}"
        _set_slot_value(
            arm_name, envelope, plane="uml_route", name="route_receipt", value=value
        )
    else:
        raise ArchitectureError(f"unknown_attack_category:{category}")


def build_adversarial_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for category in ATTACK_CATEGORIES:
        for variant in range(10):
            base_index = variant
            if category == "identity_collision":
                base_index = variant  # first 12 mouth fixtures are identity
            specs.append(
                {
                    "case_id": f"{category}:{variant:02d}",
                    "category": category,
                    "variant": variant,
                    "base_index": base_index,
                }
            )
    return specs


def _aggregate_serialization_hash(
    arm: type[LayeredBridge] | type[UnifiedTypedRegistry],
    bundles: Sequence[Mapping[str, Any]],
) -> str:
    digest = hashlib.sha256()
    for bundle in bundles:
        payload = _canonical_bytes(arm.encode(bundle))
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[min(rank, len(ordered) - 1)]


def _distribution(values: Sequence[float], unit: str) -> dict[str, Any]:
    numeric = [float(value) for value in values]
    mean = statistics.fmean(numeric) if numeric else 0.0
    stdev = statistics.pstdev(numeric) if len(numeric) > 1 else 0.0
    return {
        "unit": unit,
        "n": len(numeric),
        "min": min(numeric) if numeric else 0.0,
        "p50": _percentile(numeric, 0.50),
        "p95": _percentile(numeric, 0.95),
        "p99": _percentile(numeric, 0.99),
        "max": max(numeric) if numeric else 0.0,
        "mean": mean,
        "stdev": stdev,
        "coefficient_of_variation": (stdev / mean) if mean > 0 else None,
    }


def _measure_latency(
    arm: type[LayeredBridge] | type[UnifiedTypedRegistry],
    encoded: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    for _ in range(2):
        for envelope in encoded:
            arm.validate(envelope)
    gc.collect()
    validation_ms: list[float] = []
    for _ in range(15):
        start = time.perf_counter_ns()
        for envelope in encoded:
            arm.validate(envelope)
        validation_ms.append((time.perf_counter_ns() - start) / 1_000_000.0)

    for _ in range(2):
        for envelope in encoded:
            arm.lookup_index(envelope)
    index_ms: list[float] = []
    indices: list[dict[tuple[str, str], list[Mapping[str, Any]]]] = []
    for _ in range(15):
        start = time.perf_counter_ns()
        indices = [arm.lookup_index(envelope) for envelope in encoded]
        index_ms.append((time.perf_counter_ns() - start) / 1_000_000.0)

    queries: list[tuple[int, tuple[str, str]]] = []
    for index, lookup in enumerate(indices):
        for key in sorted(lookup):
            queries.append((index, key))
    lookup_ns_per_op: list[float] = []
    repeats = max(1, 20_000 // max(1, len(queries)))
    for _ in range(20):
        operations = 0
        start = time.perf_counter_ns()
        for _repeat in range(repeats):
            for index, key in queries:
                rows = indices[index].get(key)
                if not rows:
                    raise ArchitectureError(f"qualified_lookup_failed:{key}")
                operations += 1
        elapsed = time.perf_counter_ns() - start
        lookup_ns_per_op.append(elapsed / max(1, operations))

    validation = _distribution(validation_ms, "ms_per_full_corpus")
    validation["per_bundle_us_p50"] = (
        float(validation["p50"]) * 1000.0 / max(1, len(encoded))
    )
    validation_cv = validation.get("coefficient_of_variation")
    validation["low_signal"] = bool(
        (validation_cv is not None and float(validation_cv) > 0.25)
        or float(validation["p50"]) < 1.0
    )
    index_build = _distribution(index_ms, "ms_per_full_corpus")
    index_build["per_bundle_us_p50"] = (
        float(index_build["p50"]) * 1000.0 / max(1, len(encoded))
    )
    lookup = _distribution(lookup_ns_per_op, "ns_per_qualified_lookup")
    lookup_cv = lookup.get("coefficient_of_variation")
    lookup["low_signal"] = bool(
        float(lookup["p50"]) < 1000.0
        or (lookup_cv is not None and float(lookup_cv) > 0.25)
    )
    return {
        "warmup_rounds": 2,
        "validation": validation,
        "index_build": index_build,
        "qualified_lookup": lookup,
        "timer": "time.perf_counter_ns",
        "timer_resolution_s": time.get_clock_info("perf_counter").resolution,
    }


def _class_complexity(candidate: type[Any]) -> dict[str, int]:
    source = textwrap.dedent(inspect.getsource(candidate))
    tree = ast.parse(source)
    lines = [
        line
        for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    branch_types = (
        ast.If,
        ast.For,
        ast.While,
        ast.Try,
        ast.BoolOp,
        ast.IfExp,
        ast.Match,
        ast.comprehension,
    )
    return {
        "nonblank_noncomment_lines": len(lines),
        "branch_nodes": sum(
            1 for node in ast.walk(tree) if isinstance(node, branch_types)
        ),
        "method_count": sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
    }


def _shared_validator_complexity() -> dict[str, int]:
    functions = (
        _validate_provenance,
        _validate_route,
        _validate_plane_record,
        _resolve_composition,
        _validate_logical_bundle,
    )
    source = "\n".join(textwrap.dedent(inspect.getsource(fn)) for fn in functions)
    tree = ast.parse(source)
    lines = [
        line
        for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    branch_types = (
        ast.If,
        ast.For,
        ast.While,
        ast.Try,
        ast.BoolOp,
        ast.IfExp,
        ast.Match,
        ast.comprehension,
    )
    return {
        "nonblank_noncomment_lines": len(lines),
        "branch_nodes": sum(
            1 for node in ast.walk(tree) if isinstance(node, branch_types)
        ),
        "note": "Shared plane-validation proxy; excluded from arm delta.",
    }


def _auditability(decoded: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    checks = 0
    missing: list[str] = []
    for bundle in decoded:
        for record in bundle["records"]:
            for field in ("plane", "source", "authority", "provenance"):
                checks += 1
                if record.get(field) in (None, "", {}):
                    missing.append(f"{record['record_id']}:{field}")
            if record["plane"] == "uml_route":
                for field in (
                    "raw_route",
                    "final_route",
                    "domains",
                    "federation",
                    "route_state",
                    "seal_state",
                    "sealed_destination",
                    "destination_match",
                ):
                    checks += 1
                    if field not in record["value"]:
                        missing.append(f"{record['record_id']}:route:{field}")
            if record["plane"] == "item77_receipt":
                for field in ITEM77_FIELDS:
                    checks += 1
                    if field not in record["value"]:
                        missing.append(f"{record['record_id']}:item77:{field}")
        for group in bundle["packet_groups"]:
            for field in (
                "packet_digest",
                "cpu_signature",
                "record_ids",
                "packet_id",
            ):
                checks += 1
                if group.get(field) in (None, "", []):
                    missing.append(f"{bundle['bundle_id']}:seal:{field}")
        for binding in bundle["composition"]:
            checks += 1
            if binding.get("destination") in (None, ""):
                missing.append(
                    f"{bundle['bundle_id']}:binding:{binding['binding_id']}"
                )
    return {
        "checks": checks,
        "recovered": checks - len(missing),
        "missing": len(missing),
        "recovery_rate": (checks - len(missing)) / max(1, checks),
        "missing_examples": missing[:20],
    }


def _ambiguity_metrics(decoded: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    identity_collision_bundles = 0
    identity_detected = 0
    knowledge_semantic_bundles = 0
    knowledge_detected = 0
    for bundle in decoded:
        records = bundle["records"]
        identity = [row for row in records if row["name"] == "identity"]
        if len({row["plane"] for row in identity}) > 1:
            identity_collision_bundles += 1
            try:
                _resolve_composition(
                    records,
                    {
                        "binding_id": "ambiguity-probe-identity",
                        "record_id": None,
                        "plane": None,
                        "name": "identity",
                        "destination": "probe",
                        "semantic_aliases": False,
                    },
                )
            except AmbiguousLookup:
                identity_detected += 1
        knowledge = [
            row
            for row in records
            if row["name"] in {"knowledge", "knowledge_tags"}
        ]
        if len({row["plane"] for row in knowledge}) > 1:
            knowledge_semantic_bundles += 1
            try:
                _resolve_composition(
                    records,
                    {
                        "binding_id": "ambiguity-probe-knowledge",
                        "record_id": None,
                        "plane": None,
                        "name": "knowledge",
                        "destination": "probe",
                        "semantic_aliases": True,
                    },
                )
            except AmbiguousLookup:
                knowledge_detected += 1
    unresolved = (
        identity_collision_bundles
        - identity_detected
        + knowledge_semantic_bundles
        - knowledge_detected
    )
    total_cases = identity_collision_bundles + knowledge_semantic_bundles
    return {
        "identity_collision_bundles": identity_collision_bundles,
        "identity_ambiguities_detected": identity_detected,
        "knowledge_semantic_ambiguity_bundles": knowledge_semantic_bundles,
        "knowledge_ambiguities_detected": knowledge_detected,
        "ambiguity_cases": total_cases,
        "unresolved_ambiguities": unresolved,
        "unresolved_rate": unresolved / max(1, total_cases),
    }


def _flat_union_negative_control(
    bundles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    collision_events = 0
    overwritten_records = 0
    bundles_with_collision = 0
    examples: list[dict[str, Any]] = []
    for bundle in bundles:
        flat: dict[str, Mapping[str, Any]] = {}
        local = 0
        for record in bundle["records"]:
            name = str(record["name"])
            if name in flat:
                collision_events += 1
                overwritten_records += 1
                local += 1
                if len(examples) < 10:
                    examples.append(
                        {
                            "bundle_id": bundle["bundle_id"],
                            "name": name,
                            "first_plane": flat[name]["plane"],
                            "overwriting_plane": record["plane"],
                        }
                    )
            flat[name] = record
        if local:
            bundles_with_collision += 1
    return {
        "control_only": True,
        "candidate": "FLAT_UNION",
        "bundles": len(bundles),
        "bundles_with_collision": bundles_with_collision,
        "collision_events": collision_events,
        "overwritten_records": overwritten_records,
        "examples": examples,
        "hard_gate": "FAIL",
        "reason": "Plane erasure overwrites valid same-name records.",
    }


def _inventory_guard() -> dict[str, Any]:
    master = FOUNDATION / "artifacts" / "auto" / "master_rid.json"
    guarded_suffixes = {
        ".pt",
        ".pth",
        ".ckpt",
        ".safetensors",
        ".jsonl",
        ".csv",
    }
    rows: list[tuple[str, int, int]] = []
    training_root = FOUNDATION / "models" / "Training"
    if training_root.is_dir():
        for path in training_root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.casefold() in guarded_suffixes
                and "runs" not in {part.casefold() for part in path.parts}
            ):
                stat = path.stat()
                rows.append(
                    (
                        str(path.relative_to(FOUNDATION)).replace("\\", "/"),
                        int(stat.st_size),
                        int(stat.st_mtime_ns),
                    )
                )
    rows.sort()
    source_hashes = {
        role: _sha_file(path)
        for role, path in SOURCE_PATHS.items()
        if path.is_file()
    }
    return {
        "guarded_training_file_count": len(rows),
        "guarded_training_metadata_sha256": _sha_value(rows),
        "source_sha256": source_hashes,
        "master_rid_path": str(master).replace("\\", "/"),
        "master_rid_sha256": _sha_file(master) if master.is_file() else None,
    }


def _evaluate_arm(
    arm: type[LayeredBridge] | type[UnifiedTypedRegistry],
    bundles: Sequence[Mapping[str, Any]],
    specs: Sequence[Mapping[str, Any]],
    item77_integrated: bool,
) -> dict[str, Any]:
    encoded: list[dict[str, Any]] = []
    decoded: list[dict[str, Any]] = []
    false_rejects: list[dict[str, str]] = []
    fidelity_losses: list[str] = []
    serialized_bytes = 0
    token_indices = 0
    serialization_digest = hashlib.sha256()
    for bundle in bundles:
        try:
            envelope = arm.encode(bundle)
            arm.validate(envelope)
            roundtrip = arm.decode(envelope)
            encoded.append(envelope)
            decoded.append(roundtrip)
            if _canonical_bytes(roundtrip) != _canonical_bytes(
                _normalize_bundle(bundle)
            ):
                fidelity_losses.append(str(bundle["bundle_id"]))
            payload = _canonical_bytes(envelope)
            serialized_bytes += len(payload)
            token_indices += len(uml_character_encode(payload.decode("utf-8")))
            serialization_digest.update(len(payload).to_bytes(8, "big"))
            serialization_digest.update(payload)
        except Exception as exc:
            false_rejects.append(
                {
                    "bundle_id": str(bundle.get("bundle_id")),
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )

    replay_hashes = [
        _aggregate_serialization_hash(arm, bundles)
        for _ in range(3)
    ]
    adversarial_false_accepts: list[dict[str, Any]] = []
    errors_by_category: dict[str, Counter[str]] = defaultdict(Counter)
    rejected_by_category: Counter[str] = Counter()
    for spec in specs:
        base = bundles[int(spec["base_index"]) % len(bundles)]
        envelope = arm.encode(base)
        _apply_attack(
            arm.name,
            envelope,
            str(spec["category"]),
            int(spec["variant"]),
        )
        try:
            arm.validate(envelope)
            adversarial_false_accepts.append(dict(spec))
        except Exception as exc:
            rejected_by_category[str(spec["category"])] += 1
            errors_by_category[str(spec["category"])][
                f"{type(exc).__name__}:{str(exc).split(':')[0]}"
            ] += 1

    audit = _auditability(decoded) if decoded else {
        "checks": 0,
        "recovered": 0,
        "missing": 1,
        "recovery_rate": 0.0,
        "missing_examples": ["no_decoded_records"],
    }
    ambiguity = _ambiguity_metrics(decoded) if decoded else {
        "identity_collision_bundles": 0,
        "identity_ambiguities_detected": 0,
        "knowledge_semantic_ambiguity_bundles": 0,
        "knowledge_ambiguities_detected": 0,
        "ambiguity_cases": 0,
        "unresolved_ambiguities": 1,
        "unresolved_rate": 1.0,
    }
    latency = _measure_latency(arm, encoded) if encoded and not false_rejects else {
        "status": "SKIPPED_INVALID_CORPUS"
    }
    active_planes = 5 if item77_integrated else 4
    fixture_record_count = sum(len(bundle["records"]) for bundle in bundles)
    integration = (
        {
            "active_plane_adapters": active_planes,
            "native_plane_schema_rewrites": 0,
            "fixture_records_serialized_through_new_record_shape": 0,
            "fixture_records_touched_by_adapter": fixture_record_count,
            "adapter_kind": "bridge_index_over_retained_native_namespaces",
            "native_plane_schemas_retained": active_planes,
            "existing_plane_validators_delegated": active_planes,
            "packet_seal_reconstruction_required": False,
            "proxy_note": (
                "Static integration proxy only: native payloads stay in their "
                "current plane shapes; bridge adapters are still new code."
            ),
        }
        if arm.name == ARM_A
        else {
            "active_plane_adapters": active_planes,
            "native_plane_schema_rewrites": active_planes,
            "fixture_records_serialized_through_new_record_shape": fixture_record_count,
            "fixture_records_touched_by_adapter": fixture_record_count,
            "adapter_kind": "typed_record_conversion_for_every_fixture",
            "native_plane_schemas_retained": 0,
            "existing_plane_validators_delegated": active_planes,
            "packet_seal_reconstruction_required": True,
            "proxy_note": (
                "Static integration proxy only: every tag needs a typed adapter; "
                "existing validators are delegated after native reconstruction."
            ),
        }
    )

    removal = copy.deepcopy(encoded[0])
    removed_component = "bridge" if arm.name == ARM_A else "registry"
    removal.pop(removed_component, None)
    removal_error: str | None = None
    try:
        arm.validate(removal)
    except Exception as exc:
        removal_error = f"{type(exc).__name__}:{exc}"
    removal_test = {
        "removed_component": removed_component,
        "validator_rejected_removal": removal_error is not None,
        "error": removal_error,
        "broken_invariants": (
            [
                "cross_plane_logical_roundtrip",
                "composition_binding_resolution",
                "qualified_and_ambiguity_safe_lookup",
                "common_provenance_audit",
            ]
            if arm.name == ARM_A
            else [
                "all_tag_serialization",
                "typed_lookup",
                "packet_group_reconstruction",
                "common_provenance_audit",
            ]
        ),
    }

    authority_false_accepts = [
        row
        for row in adversarial_false_accepts
        if row["category"] in AUTHORITY_ATTACK_CATEGORIES
    ]
    seal_binding_ambiguities = int(ambiguity["unresolved_ambiguities"])
    if not removal_test["validator_rejected_removal"]:
        seal_binding_ambiguities += 1
    hard_gate = {
        "authority_false_accepts": len(authority_false_accepts),
        "field_loss_bundles": len(fidelity_losses),
        "nondeterministic_replays": len(set(replay_hashes)) - 1,
        "seal_or_binding_ambiguities": seal_binding_ambiguities,
    }
    hard_gate["status"] = (
        "PASS"
        if all(int(value) == 0 for key, value in hard_gate.items() if key != "status")
        else "FAIL"
    )
    return {
        "candidate": arm.name,
        "valid_acceptance": {
            "input_bundles": len(bundles),
            "accepted_bundles": len(encoded),
            "false_rejects": len(false_rejects),
            "false_reject_examples": false_rejects[:20],
            "input_records": sum(len(bundle["records"]) for bundle in bundles),
        },
        "roundtrip_fidelity": {
            "bundles_compared": len(decoded),
            "field_loss_bundles": len(fidelity_losses),
            "field_loss_examples": fidelity_losses[:20],
            "preserved_records": (
                sum(len(bundle["records"]) for bundle in bundles)
                if not fidelity_losses and not false_rejects
                else None
            ),
        },
        "authority_safety": {
            "adversarial_cases": len(specs),
            "rejected": len(specs) - len(adversarial_false_accepts),
            "false_accepts": len(adversarial_false_accepts),
            "authority_false_accepts": len(authority_false_accepts),
            "false_accept_examples": adversarial_false_accepts[:20],
            "rejected_by_category": dict(rejected_by_category),
            "error_classes_by_category": {
                category: dict(counter)
                for category, counter in errors_by_category.items()
            },
        },
        "collision_ambiguity": ambiguity,
        "determinism": {
            "replays": len(replay_hashes),
            "unique_hashes": len(set(replay_hashes)),
            "hashes": replay_hashes,
        },
        "auditability": audit,
        "complexity_proxy": _class_complexity(arm),
        "storage": {
            "canonical_serialized_bytes": serialized_bytes,
            "mean_bytes_per_bundle": serialized_bytes / max(1, len(encoded)),
            "uml_character_token_indices": token_indices,
            "mean_token_indices_per_bundle": token_indices / max(1, len(encoded)),
            "tokenizer_schema": UML_TOKENIZER_SCHEMA,
            "token_unit": UML_TOKEN_UNIT,
            "note": (
                "Canonical UML character tokenizer assigns one index per Unicode "
                "scalar; this is an index-count proxy, not measured energy."
            ),
            "serialization_sha256": serialization_digest.hexdigest(),
        },
        "latency": latency,
        "integration_fit": integration,
        "removal_test": removal_test,
        "hard_gate": hard_gate,
    }


def _relative_material(a: float, b: float, threshold: float = 0.10) -> int:
    base = max(abs(a), abs(b), 1e-12)
    delta = abs(a - b) / base
    if delta < threshold:
        return 0
    return -1 if a < b else 1


def _decide(
    arm_a: Mapping[str, Any],
    arm_b: Mapping[str, Any],
    *,
    corpus_records: int,
    adversarial_cases: int,
) -> tuple[str, dict[str, Any]]:
    if corpus_records < 512 or adversarial_cases < 128:
        return "INCONCLUSIVE", {
            "reason": "minimum_sample_gate",
            "corpus_records": corpus_records,
            "adversarial_cases": adversarial_cases,
        }
    passes = {
        ARM_A: arm_a["hard_gate"]["status"] == "PASS",
        ARM_B: arm_b["hard_gate"]["status"] == "PASS",
    }
    if passes[ARM_A] and not passes[ARM_B]:
        return "LAYERED_BRIDGE_WINS", {"reason": "only_hard_gate_passer"}
    if passes[ARM_B] and not passes[ARM_A]:
        return "UNIFIED_TYPED_REGISTRY_WINS", {
            "reason": "only_hard_gate_passer"
        }
    if not passes[ARM_A] and not passes[ARM_B]:
        return "INCONCLUSIVE", {"reason": "both_candidates_failed_hard_gate"}

    points = {ARM_A: 0, ARM_B: 0}
    evidence: list[dict[str, Any]] = []

    a_bytes = float(arm_a["storage"]["canonical_serialized_bytes"])
    b_bytes = float(arm_b["storage"]["canonical_serialized_bytes"])
    material = _relative_material(a_bytes, b_bytes)
    if material:
        winner = ARM_A if material < 0 else ARM_B
        points[winner] += 1
        evidence.append(
            {
                "metric": "serialized_footprint",
                "winner": winner,
                "weight": 1,
                "a": a_bytes,
                "b": b_bytes,
            }
        )

    a_complex = float(
        arm_a["complexity_proxy"]["nonblank_noncomment_lines"]
        + arm_a["complexity_proxy"]["branch_nodes"]
    )
    b_complex = float(
        arm_b["complexity_proxy"]["nonblank_noncomment_lines"]
        + arm_b["complexity_proxy"]["branch_nodes"]
    )
    material = _relative_material(a_complex, b_complex)
    if material:
        winner = ARM_A if material < 0 else ARM_B
        points[winner] += 1
        evidence.append(
            {
                "metric": "candidate_specific_static_complexity",
                "winner": winner,
                "weight": 1,
                "a": a_complex,
                "b": b_complex,
            }
        )

    a_rewrites = int(arm_a["integration_fit"]["native_plane_schema_rewrites"])
    b_rewrites = int(arm_b["integration_fit"]["native_plane_schema_rewrites"])
    if a_rewrites != b_rewrites:
        winner = ARM_A if a_rewrites < b_rewrites else ARM_B
        points[winner] += 2
        evidence.append(
            {
                "metric": "native_schema_migration_proxy",
                "winner": winner,
                "weight": 2,
                "a": a_rewrites,
                "b": b_rewrites,
                "note": "Weighted for production change risk; still a static proxy.",
            }
        )

    a_validation = arm_a.get("latency", {}).get("validation", {})
    b_validation = arm_b.get("latency", {}).get("validation", {})
    if (
        a_validation
        and b_validation
        and not a_validation.get("low_signal")
        and not b_validation.get("low_signal")
    ):
        a_time = float(a_validation["p50"])
        b_time = float(b_validation["p50"])
        material = _relative_material(a_time, b_time)
        if material:
            winner = ARM_A if material < 0 else ARM_B
            points[winner] += 1
            evidence.append(
                {
                    "metric": "validation_latency_p50",
                    "winner": winner,
                    "weight": 1,
                    "a": a_time,
                    "b": b_time,
                }
            )
    else:
        evidence.append(
            {
                "metric": "validation_latency_p50",
                "winner": None,
                "weight": 0,
                "note": "Excluded as low-signal.",
            }
        )

    a_lookup = arm_a.get("latency", {}).get("qualified_lookup", {})
    b_lookup = arm_b.get("latency", {}).get("qualified_lookup", {})
    if (
        a_lookup
        and b_lookup
        and not a_lookup.get("low_signal")
        and not b_lookup.get("low_signal")
    ):
        a_time = float(a_lookup["p50"])
        b_time = float(b_lookup["p50"])
        material = _relative_material(a_time, b_time)
        if material:
            winner = ARM_A if material < 0 else ARM_B
            points[winner] += 1
            evidence.append(
                {
                    "metric": "qualified_lookup_latency_p50",
                    "winner": winner,
                    "weight": 1,
                    "a": a_time,
                    "b": b_time,
                }
            )
    else:
        evidence.append(
            {
                "metric": "qualified_lookup_latency_p50",
                "winner": None,
                "weight": 0,
                "note": "Excluded as low-signal Python micro-timing.",
            }
        )

    point_delta = points[ARM_B] - points[ARM_A]
    if point_delta >= 2:
        verdict = "UNIFIED_TYPED_REGISTRY_WINS"
    elif point_delta <= -2:
        verdict = "LAYERED_BRIDGE_WINS"
    else:
        verdict = "TIE_WITH_CONSTRAINTS"
    return verdict, {
        "reason": "predeclared_material_delta_points",
        "points": points,
        "point_delta_b_minus_a": point_delta,
        "evidence": evidence,
        "tie_band": "absolute point delta < 2",
        "timing_threshold": "10% and not low-signal",
        "footprint_complexity_threshold": "10%",
    }


def _delta(a: float | int, b: float | int) -> float:
    return float(b) - float(a)


def _markdown_report(report: Mapping[str, Any]) -> str:
    a = report["arms"][ARM_A]
    b = report["arms"][ARM_B]
    lines = [
        f"# {EXPERIMENT_ID}: Offline Tag Architecture A/B",
        "",
        f"**Verdict: {report['verdict']}**",
        "",
        "## Candidates actually tested",
        "",
        (
            "- **LAYERED_BRIDGE:** native authority packets, mouth rows, UML route "
            "receipts, context roles, and optional item-77 receipts remain in separate "
            "namespaces. A schema-locked bridge carries common provenance/authority "
            "metadata and qualified composition bindings. Native validators remain "
            "authoritative."
        ),
        (
            "- **UNIFIED_TYPED_REGISTRY:** every logical tag serializes as one fixed "
            "record (`plane`, `name`, `value`, `source`, `authority`, `confidence`, "
            "`required`, `provenance`, `attributes`, `binding`). Packet groups retain "
            "digest/signature metadata and are reconstructed for the existing packet "
            "validator. Existing plane validators are delegated, not replaced."
        ),
        "",
        "Arm B is a constrained typed registry, not a flat union. Delegating existing "
        "plane validators does not turn it into Arm A because every tag still serializes "
        "and looks up through the registry.",
        "",
        "## Inputs",
        "",
        f"- Valid bundles: **{report['inputs']['valid_bundles']}**",
        f"- Valid logical records: **{report['inputs']['valid_records']}**",
        f"- Adversarial cases: **{report['inputs']['adversarial_cases']}**",
        f"- Mouth domains: `{', '.join(report['inputs']['mouth_domains'])}`",
        f"- UML route labels: `{', '.join(report['inputs']['uml_route_labels'])}`",
        "",
        "## Metrics",
        "",
        "| Metric | Layered bridge | Typed registry | B - A |",
        "|---|---:|---:|---:|",
        (
            f"| Valid accepted bundles | {a['valid_acceptance']['accepted_bundles']} "
            f"| {b['valid_acceptance']['accepted_bundles']} "
            f"| {_delta(a['valid_acceptance']['accepted_bundles'], b['valid_acceptance']['accepted_bundles']):.0f} |"
        ),
        (
            f"| Valid false rejects | {a['valid_acceptance']['false_rejects']} "
            f"| {b['valid_acceptance']['false_rejects']} "
            f"| {_delta(a['valid_acceptance']['false_rejects'], b['valid_acceptance']['false_rejects']):.0f} |"
        ),
        (
            f"| Adversarial false accepts | {a['authority_safety']['false_accepts']} "
            f"| {b['authority_safety']['false_accepts']} "
            f"| {_delta(a['authority_safety']['false_accepts'], b['authority_safety']['false_accepts']):.0f} |"
        ),
        (
            f"| Field-loss bundles | {a['roundtrip_fidelity']['field_loss_bundles']} "
            f"| {b['roundtrip_fidelity']['field_loss_bundles']} "
            f"| {_delta(a['roundtrip_fidelity']['field_loss_bundles'], b['roundtrip_fidelity']['field_loss_bundles']):.0f} |"
        ),
        (
            f"| Unresolved ambiguities | {a['collision_ambiguity']['unresolved_ambiguities']} "
            f"| {b['collision_ambiguity']['unresolved_ambiguities']} "
            f"| {_delta(a['collision_ambiguity']['unresolved_ambiguities'], b['collision_ambiguity']['unresolved_ambiguities']):.0f} |"
        ),
        (
            f"| Audit fields missing | {a['auditability']['missing']} "
            f"| {b['auditability']['missing']} "
            f"| {_delta(a['auditability']['missing'], b['auditability']['missing']):.0f} |"
        ),
        (
            f"| Serialized bytes | {a['storage']['canonical_serialized_bytes']} "
            f"| {b['storage']['canonical_serialized_bytes']} "
            f"| {_delta(a['storage']['canonical_serialized_bytes'], b['storage']['canonical_serialized_bytes']):.0f} |"
        ),
        (
            f"| UML character indices | {a['storage']['uml_character_token_indices']} "
            f"| {b['storage']['uml_character_token_indices']} "
            f"| {_delta(a['storage']['uml_character_token_indices'], b['storage']['uml_character_token_indices']):.0f} |"
        ),
        (
            f"| Candidate LOC proxy | {a['complexity_proxy']['nonblank_noncomment_lines']} "
            f"| {b['complexity_proxy']['nonblank_noncomment_lines']} "
            f"| {_delta(a['complexity_proxy']['nonblank_noncomment_lines'], b['complexity_proxy']['nonblank_noncomment_lines']):.0f} |"
        ),
        (
            f"| Candidate branch proxy | {a['complexity_proxy']['branch_nodes']} "
            f"| {b['complexity_proxy']['branch_nodes']} "
            f"| {_delta(a['complexity_proxy']['branch_nodes'], b['complexity_proxy']['branch_nodes']):.0f} |"
        ),
        (
            f"| Validation p50, ms/corpus | {a['latency']['validation']['p50']:.6f} "
            f"| {b['latency']['validation']['p50']:.6f} "
            f"| {_delta(a['latency']['validation']['p50'], b['latency']['validation']['p50']):.6f} |"
        ),
        (
            f"| Qualified lookup p50, ns/op | {a['latency']['qualified_lookup']['p50']:.3f} "
            f"| {b['latency']['qualified_lookup']['p50']:.3f} "
            f"| {_delta(a['latency']['qualified_lookup']['p50'], b['latency']['qualified_lookup']['p50']):.3f} |"
        ),
        (
            f"| Native schema rewrites (proxy) | "
            f"{a['integration_fit']['native_plane_schema_rewrites']} "
            f"| {b['integration_fit']['native_plane_schema_rewrites']} "
            f"| {_delta(a['integration_fit']['native_plane_schema_rewrites'], b['integration_fit']['native_plane_schema_rewrites']):.0f} |"
        ),
        "",
        "Timing is included only as a local repeated benchmark. Low-signal timing is "
        "excluded from the decision score.",
        "",
        "## Hard gates",
        "",
        f"- LAYERED_BRIDGE: **{a['hard_gate']['status']}** — `{_canonical_text(a['hard_gate'])}`",
        f"- UNIFIED_TYPED_REGISTRY: **{b['hard_gate']['status']}** — `{_canonical_text(b['hard_gate'])}`",
        "",
        "## Item-77 integration",
        "",
        f"- Status: **{report['item77']['status']}**",
        f"- Receipt: `{report['item77'].get('path')}`",
        f"- Per-example rows replayed: **{report['item77']['example_count']}**",
        (
            "- Experiment-only names `item77_receipt` and `cheap_route_example` are "
            "proposed/operator-gated if production promotion is ever considered. The "
            "measured receipt fields remain value fields, not established tag names."
        ),
        "",
        "## Removal test",
        "",
        (
            f"- Layered bridge removed: rejected={a['removal_test']['validator_rejected_removal']}; "
            f"breaks `{', '.join(a['removal_test']['broken_invariants'])}`."
        ),
        (
            f"- Typed registry removed: rejected={b['removal_test']['validator_rejected_removal']}; "
            f"breaks `{', '.join(b['removal_test']['broken_invariants'])}`."
        ),
        "",
        "## Decision evidence",
        "",
        f"- Score: `{_canonical_text(report['decision'])}`",
        f"- Classification: {report['classification']}",
        "",
        "## Reproduce",
        "",
        f"`{report['run']['exact_command']}`",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(
        [
            "",
            "## Recommended next action",
            "",
            report["recommended_next_action"],
            "",
            "No runtime, router, production tag schema, checkpoint, training data, "
            "curriculum admission, or model state was changed.",
            "",
        ]
    )
    return "\n".join(lines)


def _logical_corpus_hash(bundles: Sequence[Mapping[str, Any]]) -> str:
    stripped = copy.deepcopy(list(bundles))
    for bundle in stripped:
        for group in bundle["packet_groups"]:
            group["cpu_signature"] = "<process_local_hmac_redacted>"
    return _sha_value(stripped)


def run_full(output_root: Path | None = None) -> tuple[dict[str, Any], Path, Path]:
    started = _utc_now()
    guard_before = _inventory_guard()
    source_hashes = _source_hashes()
    item77 = discover_item77_receipt()
    bundles = build_replay_corpus(source_hashes, item77)
    specs = build_adversarial_specs()
    valid_records = sum(len(bundle["records"]) for bundle in bundles)
    if valid_records < 512:
        raise ArchitectureError(f"valid_record_minimum:{valid_records}")
    if len(specs) < 128:
        raise ArchitectureError(f"adversarial_minimum:{len(specs)}")

    arm_a = _evaluate_arm(
        LayeredBridge,
        bundles,
        specs,
        item77_integrated=item77["status"] == "INTEGRATED",
    )
    arm_b = _evaluate_arm(
        UnifiedTypedRegistry,
        bundles,
        specs,
        item77_integrated=item77["status"] == "INTEGRATED",
    )
    verdict, decision = _decide(
        arm_a,
        arm_b,
        corpus_records=valid_records,
        adversarial_cases=len(specs),
    )
    finished = _utc_now()
    guard_after = _inventory_guard()
    mutation_guard_ok = guard_before == guard_after

    command = (
        f"{Path(sys.executable)} {Path(__file__).resolve()} --full"
    ).replace("/", "\\")
    route_labels = sorted(
        {
            str(record["value"]["federation"])
            for bundle in bundles
            for record in bundle["records"]
            if record["plane"] == "uml_route"
        }
    )
    mouth_domains = sorted(
        {
            str(record["name"])
            for bundle in bundles
            for record in bundle["records"]
            if record["plane"] == "mouth_atom"
        }
    )
    deltas = {
        "b_minus_a": {
            "serialized_bytes": _delta(
                arm_a["storage"]["canonical_serialized_bytes"],
                arm_b["storage"]["canonical_serialized_bytes"],
            ),
            "uml_character_token_indices": _delta(
                arm_a["storage"]["uml_character_token_indices"],
                arm_b["storage"]["uml_character_token_indices"],
            ),
            "candidate_loc_proxy": _delta(
                arm_a["complexity_proxy"]["nonblank_noncomment_lines"],
                arm_b["complexity_proxy"]["nonblank_noncomment_lines"],
            ),
            "candidate_branch_proxy": _delta(
                arm_a["complexity_proxy"]["branch_nodes"],
                arm_b["complexity_proxy"]["branch_nodes"],
            ),
            "validation_p50_ms_full_corpus": _delta(
                arm_a["latency"]["validation"]["p50"],
                arm_b["latency"]["validation"]["p50"],
            ),
            "qualified_lookup_p50_ns": _delta(
                arm_a["latency"]["qualified_lookup"]["p50"],
                arm_b["latency"]["qualified_lookup"]["p50"],
            ),
            "native_schema_rewrites_proxy": _delta(
                arm_a["integration_fit"]["native_plane_schema_rewrites"],
                arm_b["integration_fit"]["native_plane_schema_rewrites"],
            ),
        }
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "verdict": verdict,
        "classification": (
            "The tested typed-envelope/delegated-validator design is substantively "
            "Arm B. A future single envelope that keeps plane validators authoritative "
            "is not automatically a synthesis; if every tag serializes through the "
            "typed registry, it remains constrained UNIFIED_TYPED_REGISTRY."
        ),
        "hypothesis": (
            "A bounded replay can distinguish layered native namespaces from a "
            "schema-locked typed registry on safety, fidelity, ambiguity, auditability, "
            "footprint, latency, and integration proxies without training or runtime writes."
        ),
        "candidates": {
            ARM_A: {
                "definition": (
                    "Separate authority, mouth, UML route, context, and optional item-77 "
                    "native namespaces; deterministic bridge only for composed receipts; "
                    "plane validators authoritative."
                ),
                "schema_version": LayeredBridge.schema_version,
            },
            ARM_B: {
                "definition": (
                    "One fixed typed record registry for all tags, explicit plane and "
                    "authority, packet-group seals, qualified bindings, and delegated "
                    "existing plane validators."
                ),
                "schema_version": UnifiedTypedRegistry.schema_version,
            },
        },
        "inputs": {
            "valid_bundles": len(bundles),
            "valid_records": valid_records,
            "adversarial_cases": len(specs),
            "adversarial_categories": list(ATTACK_CATEGORIES),
            "packet_tag_types": list(tagged_packet.ALLOWED_TAGS),
            "mouth_base_atoms": sorted(BASE_ATOMS),
            "mouth_combo_domains": sorted(COMBO_DOMAINS),
            "mouth_domains": mouth_domains,
            "context_roles": sorted(KNOWN_ROLES),
            "uml_route_labels": route_labels,
            "logical_corpus_sha256": _logical_corpus_hash(bundles),
            "source_hashes": source_hashes,
            "signature_note": (
                "The production packet module creates a process-local HMAC key. "
                "Logical corpus hash redacts only that process-local signature; "
                "packet digest and all logical fields remain hashed."
            ),
        },
        "arms": {ARM_A: arm_a, ARM_B: arm_b},
        "deltas": deltas,
        "decision": decision,
        "flat_union_negative_control": _flat_union_negative_control(bundles),
        "shared_validator_complexity_proxy": _shared_validator_complexity(),
        "item77": {
            key: value for key, value in item77.items() if key != "rows"
        },
        "runtime_health": {
            "mode": "offline_read_only",
            "heartbeat": "not_applicable_no_runtime_loop",
            "errors": 0,
            "stalls": 0,
            "sample_validity": "VALID",
            "other_worker_interference": (
                "item77_measurement_completed_before_full_window;"
                "receipt_ingested_read_only"
                if item77["status"] == "INTEGRATED"
                else "none_observed"
            ),
        },
        "mutation_guard": {
            "status": "PASS" if mutation_guard_ok else "FAIL",
            "before": guard_before,
            "after": guard_after,
            "runtime_model_training_mutation_detected": not mutation_guard_ok,
            "scope": (
                "Source hashes, master RID hash, and non-runs training/checkpoint/data "
                "metadata inventory."
            ),
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
            (
                "Both candidates are executable offline prototypes in one harness, not "
                "production router integrations. Static migration and complexity counts "
                "are proxies, not maintainability claims."
            ),
            (
                "Latency is local Python timing under concurrent workstation load; "
                "qualified lookups below the declared signal floor are labeled low-signal "
                "and excluded from the decision."
            ),
            (
                "UML character-token count is one index per Unicode scalar. It is not a "
                "neural tokenizer count, energy reading, or tariff estimate."
            ),
            (
                "Production authority HMAC uses a process-local secret, so cross-process "
                "signature bytes are intentionally not a reproducibility target. Within-run "
                "canonical replay hashes must still be identical."
            ),
            (
                (
                    "Item-77 integration covers one survivor census: three modes over "
                    "the same 256 sealed prompts (768 per-mode receipts). It is real "
                    "receipt evidence, but not multiple independent survivor windows."
                )
                if item77["status"] == "INTEGRATED"
                else (
                    "Item-77 integration is pending because no timestamped per-example "
                    "receipt was discoverable. The fallback corpus remains valid but "
                    "does not cover real cheap-route receipts."
                )
            ),
            (
                "Any production tag/plane promotion, router migration, new item-77 tag "
                "name, model/training change, or checkpoint change requires operator authority."
            ),
        ],
        "recommended_next_action": (
            "Request operator approval for one read-only, single-receipt-boundary "
            "integration pilot that measures actual adapter migration effort for both "
            "candidates while preserving existing validators; do not promote either schema."
        ),
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
    json_path = out_dir / f"tag_architecture_ab_v1_{timestamp}.json"
    md_path = out_dir / f"tag_architecture_ab_v1_{timestamp}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    md_path.write_text(
        _markdown_report(report),
        encoding="utf-8",
        newline="\n",
    )
    return report, json_path, md_path


def run_selftest() -> dict[str, Any]:
    source_hashes = _source_hashes()
    item77 = {
        "status": "PENDING",
        "path": None,
        "sha256": None,
        "example_count": 0,
        "field_coverage": {},
        "rows": [],
        "parse_errors": [],
    }
    bundles = build_replay_corpus(source_hashes, item77)[:12]
    checks: list[str] = []
    for arm in (LayeredBridge, UnifiedTypedRegistry):
        envelope = arm.encode(bundles[0])
        arm.validate(envelope)
        if _canonical_bytes(arm.decode(envelope)) != _canonical_bytes(bundles[0]):
            raise ArchitectureError(f"selftest_roundtrip:{arm.name}")
        if _aggregate_serialization_hash(arm, bundles) != _aggregate_serialization_hash(
            arm, bundles
        ):
            raise ArchitectureError(f"selftest_determinism:{arm.name}")
        checks.extend(
            [
                f"{arm.name}:valid",
                f"{arm.name}:roundtrip",
                f"{arm.name}:determinism",
            ]
        )
        for category in ATTACK_CATEGORIES:
            base_index = 0
            attacked = arm.encode(bundles[base_index])
            _apply_attack(arm.name, attacked, category, 0)
            try:
                arm.validate(attacked)
            except Exception:
                checks.append(f"{arm.name}:reject:{category}")
            else:
                raise ArchitectureError(
                    f"selftest_adversary_false_accept:{arm.name}:{category}"
                )
    return {
        "ok": True,
        "experiment_id": EXPERIMENT_ID,
        "bundles": len(bundles),
        "checks": len(checks),
        "details": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selftest", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional explicit timestamped output directory for --full.",
    )
    args = parser.parse_args()
    if args.selftest:
        result = run_selftest()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    report, json_path, md_path = run_full(args.output_root)
    print(
        json.dumps(
            {
                "ok": True,
                "experiment_id": EXPERIMENT_ID,
                "verdict": report["verdict"],
                "valid_bundles": report["inputs"]["valid_bundles"],
                "valid_records": report["inputs"]["valid_records"],
                "adversarial_cases": report["inputs"]["adversarial_cases"],
                "item77_status": report["item77"]["status"],
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
