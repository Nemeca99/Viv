"""Security ingress/egress gate wrapping field-scoped UML bridge invoke.

Contract
--------
The UML bridge is **not** a new authority plane. Security IN/OUT wraps UML
invoke and remains an external membrane. This module decides whether a packet
may enter UML and whether a write-back is admissible.

Public API (importable by the canary / bridge)::

    security_in(packet)  -> GateReceipt / dict
    security_out(packet, uml_resolved) -> GateReceipt / dict

IN:
  - sealed ``uml_request`` with CPU authority → allow, may_invoke_uml=True
  - explicitly none / absent ``uml_request`` → allow, may_invoke_uml=False
  - gpu-minted or ambiguous → deny (fail-closed)

OUT:
  - write scope = ``uml_resolved`` only
  - no invented authority tags
  - fail-closed on ambiguity

Does not start AIOS. Integrates with ``security_core`` / ``cpu_mouth_contract``
when importable; structural verdicts still apply when they are absent.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

SCHEMA_VERSION = "uml_bridge_security_gate_v1"
WRITE_SCOPE = ("uml_resolved",)

# Align with voice_core.intent_packet.UML_REQUEST_CPU_SOURCES /
# uml_field_scoped_bridge._CPU_SOURCES — do not invent a parallel set.
CPU_SOURCES = frozenset({"cpu", "cpu_identity", "cpu_authority", "operator"})
GPU_SOURCES = frozenset(
    {
        "gpu",
        "gpu_mouth",
        "gpu_render",
        "gpu_model",
        "renderer",
        "mouth",
    }
)

# Keys that would mint or internalize an authority plane inside uml_resolved.
FORBIDDEN_AUTHORITY_KEYS = frozenset(
    {
        "allowed",
        "authority",
        "authority_minted",
        "authority_handle",
        "decision_authority",
        "renderer_authority",
        "fact_authority",
        "security_plane",
        "security_ingress",
        "security_egress",
        "security_in",
        "security_out",
        "allowed_actions",
        "ingress_gate",
        "egress_gate",
        "enforce_morality",
        "constitution",
    }
)

_SEALED_KIND = "sealed_destination"


@dataclass
class GateReceipt:
    """Receipt for one Security IN/OUT decision (always emitted)."""

    allowed: bool
    stage: str
    direction: str
    reason: str
    fail_closed: bool
    may_invoke_uml: bool = False
    write_scope: tuple[str, ...] = ()
    security_plane: str = "external"
    authority_minted: bool = False
    packet_digest: str | None = None
    uml_request_present: bool | None = None
    uml_request_source: str | None = None
    sealed: bool | None = None
    forbidden_keys: tuple[str, ...] = ()
    membrane: dict[str, Any] | None = None
    mouth_contract: dict[str, Any] | None = None
    detail: str | None = None
    s_n: float | None = None
    elapsed_ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "allowed": self.allowed,
            "stage": self.stage,
            "direction": self.direction,
            "reason": self.reason,
            "fail_closed": self.fail_closed,
            "may_invoke_uml": self.may_invoke_uml,
            "write_scope": list(self.write_scope),
            "security_plane": self.security_plane,
            "authority_minted": self.authority_minted,
            "packet_digest": self.packet_digest,
            "uml_request_present": self.uml_request_present,
            "uml_request_source": self.uml_request_source,
            "sealed": self.sealed,
            "forbidden_keys": list(self.forbidden_keys),
            "membrane": self.membrane,
            "mouth_contract": self.mouth_contract,
            "detail": self.detail,
            "s_n": self.s_n,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.extra:
            out["extra"] = dict(self.extra)
        return out


def _sha(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _deny(
    *,
    stage: str,
    direction: str,
    reason: str,
    t0: float,
    s_n: float | None = None,
    may_invoke_uml: bool = False,
    write_scope: tuple[str, ...] = (),
    detail: str | None = None,
    packet_digest: str | None = None,
    uml_request_present: bool | None = None,
    uml_request_source: str | None = None,
    sealed: bool | None = None,
    forbidden_keys: tuple[str, ...] = (),
    membrane: dict[str, Any] | None = None,
    mouth_contract: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> GateReceipt:
    return GateReceipt(
        allowed=False,
        stage=stage,
        direction=direction,
        reason=reason,
        fail_closed=True,
        may_invoke_uml=may_invoke_uml,
        write_scope=write_scope,
        security_plane="external",
        authority_minted=False,
        packet_digest=packet_digest,
        uml_request_present=uml_request_present,
        uml_request_source=uml_request_source,
        sealed=sealed,
        forbidden_keys=forbidden_keys,
        membrane=membrane,
        mouth_contract=mouth_contract,
        detail=detail,
        s_n=s_n,
        elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        extra=dict(extra or {}),
    )


def _allow(
    *,
    stage: str,
    direction: str,
    reason: str,
    t0: float,
    s_n: float | None = None,
    may_invoke_uml: bool = False,
    write_scope: tuple[str, ...] = (),
    detail: str | None = None,
    packet_digest: str | None = None,
    uml_request_present: bool | None = None,
    uml_request_source: str | None = None,
    sealed: bool | None = None,
    membrane: dict[str, Any] | None = None,
    mouth_contract: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> GateReceipt:
    return GateReceipt(
        allowed=True,
        stage=stage,
        direction=direction,
        reason=reason,
        fail_closed=False,
        may_invoke_uml=may_invoke_uml,
        write_scope=write_scope,
        security_plane="external",
        authority_minted=False,
        packet_digest=packet_digest,
        uml_request_present=uml_request_present,
        uml_request_source=uml_request_source,
        sealed=sealed,
        membrane=membrane,
        mouth_contract=mouth_contract,
        detail=detail,
        s_n=s_n,
        elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        extra=dict(extra or {}),
    )


def _consult_membrane(
    *,
    stage: str,
    text: str,
    s_n: float,
) -> dict[str, Any]:
    """Best-effort consult of Rust security_core via membrane. Never mints authority."""
    try:
        from lib.security_bridge import rust_available, rust_error
        from lib.security_membrane import egress_gate, ingress_gate
    except Exception as exc:  # noqa: BLE001 — gate must stay local-first
        return {
            "consulted": False,
            "available": False,
            "reason": "security_import_failed",
            "detail": repr(exc),
            "security_plane": "external",
            "authority_minted": False,
        }

    if not rust_available():
        return {
            "consulted": False,
            "available": False,
            "reason": f"security_core_unavailable:{rust_error()}",
            "security_plane": "external",
            "authority_minted": False,
        }

    if stage == "IN":
        verdict = dict(ingress_gate(str(text), float(s_n)))
    else:
        verdict = dict(egress_gate(str(text), float(s_n)))
    verdict["consulted"] = True
    verdict["available"] = True
    verdict["security_plane"] = "external"
    verdict["authority_minted"] = False
    return verdict


def _mouth_contract_probe() -> dict[str, Any]:
    """Record whether cpu_mouth_contract is importable (no AIOS start)."""
    try:
        from lib import cpu_mouth_contract as cmc  # noqa: F401

        return {
            "present": True,
            "schema_version": getattr(cmc, "SCHEMA_VERSION", None),
            "renderer_authority": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {"present": False, "reason": repr(exc)}


def _local_seal_uml_request(
    uml_request: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Structural seal matching intent_packet.seal_uml_request (no rewrite)."""
    source = str(uml_request.get("source") or "cpu")
    if source not in CPU_SOURCES:
        return None, f"uml_request_source={source}"
    proposals = uml_request.get("proposals")
    if proposals is not None and not isinstance(proposals, list):
        return None, "uml_request_proposals_not_list"
    sealed = {
        "request_kind": uml_request.get("request_kind"),
        "target_char": uml_request.get("target_char"),
        "target_value": uml_request.get("target_value"),
        "proposals": None if proposals is None else list(proposals),
        "prefer_policy": str(uml_request.get("prefer_policy") or "cheapest_valid"),
        "source": source,
    }
    return sealed, None


def _try_seal_uml_request(
    uml_request: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Reuse intent_packet seal without rewriting it. Returns (sealed, error)."""
    try:
        from voice_core.intent_packet import UmlRequestIngressError, seal_uml_request

        try:
            return seal_uml_request(uml_request), None
        except UmlRequestIngressError as exc:
            return None, str(exc)
    except ImportError:
        return _local_seal_uml_request(uml_request)


def _source_class(source: str) -> str:
    if source in GPU_SOURCES or source.startswith("gpu"):
        return "gpu"
    if source in CPU_SOURCES:
        return "cpu"
    return "unknown"


def _validate_sealed_shape(sealed: Mapping[str, Any]) -> str | None:
    """Return deny-reason if sealed request is ambiguous / incomplete."""
    kind = sealed.get("request_kind")
    if kind is None or kind == "":
        return "ambiguous_request_kind"
    if not isinstance(kind, str):
        return "ambiguous_request_kind_type"
    if kind == "invented_binding":
        return "invented_binding"
    if kind != _SEALED_KIND:
        return f"unsupported_request_kind:{kind}"
    ch = sealed.get("target_char")
    val = sealed.get("target_value")
    if ch is None and val is None:
        return "ambiguous_or_missing_destination"
    if ch is not None and not isinstance(ch, (str, int)):
        return "ambiguous_target_char"
    if val is not None and not isinstance(val, (int, float, str)):
        return "ambiguous_target_value"
    return None


def security_in(
    packet: Mapping[str, Any] | None,
    *,
    s_n: float = 0.95,
    consult_membrane: bool = True,
) -> GateReceipt:
    """Verify packet may invoke UML (sealed uml_request or explicitly none).

    Fail-closed on ambiguity. Rejects gpu-minted ``uml_request``. Does not
    mint Security authority. Returns a full receipt on every path.
    """
    t0 = time.perf_counter()
    stage = "security_in"
    direction = "IN"
    mouth = _mouth_contract_probe()
    s_n_f = float(s_n)

    if packet is None or not isinstance(packet, Mapping):
        return _deny(
            stage=stage,
            direction=direction,
            reason="ambiguous_packet",
            t0=t0,
            s_n=s_n_f,
            detail="packet_not_mapping",
            mouth_contract=mouth,
        )

    digest = _sha(_opaque_for_digest(packet))
    has_key = "uml_request" in packet
    raw = packet.get("uml_request") if has_key else None

    # Explicitly none / absent → packet OK, UML must not be invoked.
    if (not has_key) or raw is None:
        return _allow(
            stage=stage,
            direction=direction,
            reason="explicit_none",
            t0=t0,
            s_n=s_n_f,
            may_invoke_uml=False,
            packet_digest=digest,
            uml_request_present=False,
            sealed=False,
            detail="uml_request absent or None — UML invoke forbidden",
            mouth_contract=mouth,
            membrane={"consulted": False, "skipped": "no_uml_request"},
        )

    if not isinstance(raw, Mapping):
        return _deny(
            stage=stage,
            direction=direction,
            reason="ambiguous_uml_request",
            t0=t0,
            s_n=s_n_f,
            packet_digest=digest,
            uml_request_present=True,
            sealed=False,
            detail=f"uml_request_type={type(raw).__name__}",
            mouth_contract=mouth,
        )

    source = str(raw.get("source") or "cpu")
    src_class = _source_class(source)
    if src_class == "gpu":
        return _deny(
            stage=stage,
            direction=direction,
            reason="gpu_minted_rejected",
            t0=t0,
            s_n=s_n_f,
            packet_digest=digest,
            uml_request_present=True,
            uml_request_source=source,
            sealed=False,
            detail=f"uml_request_source={source}",
            mouth_contract=mouth,
        )
    if src_class != "cpu":
        return _deny(
            stage=stage,
            direction=direction,
            reason="authority_violation",
            t0=t0,
            s_n=s_n_f,
            packet_digest=digest,
            uml_request_present=True,
            uml_request_source=source,
            sealed=False,
            detail=f"uml_request_source={source}",
            mouth_contract=mouth,
        )

    sealed, seal_err = _try_seal_uml_request(raw)
    if sealed is None:
        return _deny(
            stage=stage,
            direction=direction,
            reason="seal_failed",
            t0=t0,
            s_n=s_n_f,
            packet_digest=digest,
            uml_request_present=True,
            uml_request_source=source,
            sealed=False,
            detail=seal_err,
            mouth_contract=mouth,
        )

    shape_err = _validate_sealed_shape(sealed)
    if shape_err is not None:
        return _deny(
            stage=stage,
            direction=direction,
            reason=shape_err,
            t0=t0,
            s_n=s_n_f,
            packet_digest=digest,
            uml_request_present=True,
            uml_request_source=str(sealed.get("source") or source),
            sealed=False,
            detail=shape_err,
            mouth_contract=mouth,
        )

    membrane: dict[str, Any] | None = None
    if consult_membrane:
        ingress_text = json.dumps(
            {
                "gate": SCHEMA_VERSION,
                "request_kind": sealed.get("request_kind"),
                "target_char": sealed.get("target_char"),
                "target_value": sealed.get("target_value"),
                "source": sealed.get("source"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        membrane = _consult_membrane(stage="IN", text=ingress_text, s_n=s_n_f)
        if membrane.get("consulted") and not membrane.get("allowed", False):
            return _deny(
                stage=stage,
                direction=direction,
                reason="membrane_denied",
                t0=t0,
                s_n=s_n_f,
                packet_digest=digest,
                uml_request_present=True,
                uml_request_source=str(sealed.get("source") or source),
                sealed=True,
                detail=str(membrane.get("reason") or "security_in_blocked"),
                membrane=membrane,
                mouth_contract=mouth,
            )

    return _allow(
        stage=stage,
        direction=direction,
        reason="sealed_uml_request",
        t0=t0,
        s_n=s_n_f,
        may_invoke_uml=True,
        packet_digest=digest,
        uml_request_present=True,
        uml_request_source=str(sealed.get("source") or source),
        sealed=True,
        detail="cpu sealed uml_request admitted",
        membrane=membrane,
        mouth_contract=mouth,
        extra={"sealed_uml_request": copy.deepcopy(dict(sealed))},
    )


def _opaque_for_digest(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Digest view excluding uml_resolved write-back slot."""
    return {k: v for k, v in packet.items() if k != "uml_resolved"}


def _collect_forbidden(obj: Mapping[str, Any]) -> list[str]:
    hits: list[str] = []
    for key in obj:
        if key in FORBIDDEN_AUTHORITY_KEYS:
            hits.append(str(key))
    return sorted(hits)


def security_out(
    packet: Mapping[str, Any] | None,
    uml_resolved: Mapping[str, Any] | None,
    *,
    s_n: float = 0.95,
    consult_membrane: bool = True,
) -> GateReceipt:
    """Verify write-back is uml_resolved-only; reject invented authority tags.

    Fail-closed on ambiguity. Does not mint Security authority.
    """
    t0 = time.perf_counter()
    stage = "security_out"
    direction = "OUT"
    mouth = _mouth_contract_probe()
    s_n_f = float(s_n)
    write_scope = WRITE_SCOPE

    if packet is None or not isinstance(packet, Mapping):
        return _deny(
            stage=stage,
            direction=direction,
            reason="ambiguous_packet",
            t0=t0,
            s_n=s_n_f,
            write_scope=write_scope,
            detail="packet_not_mapping",
            mouth_contract=mouth,
        )

    digest = _sha(_opaque_for_digest(packet))

    if uml_resolved is None:
        return _deny(
            stage=stage,
            direction=direction,
            reason="missing_uml_resolved",
            t0=t0,
            s_n=s_n_f,
            write_scope=write_scope,
            packet_digest=digest,
            detail="uml_resolved required for egress write-back",
            mouth_contract=mouth,
        )

    if not isinstance(uml_resolved, Mapping):
        return _deny(
            stage=stage,
            direction=direction,
            reason="ambiguous_uml_resolved",
            t0=t0,
            s_n=s_n_f,
            write_scope=write_scope,
            packet_digest=digest,
            detail=f"uml_resolved_type={type(uml_resolved).__name__}",
            mouth_contract=mouth,
        )

    forbidden = _collect_forbidden(uml_resolved)
    if forbidden:
        return _deny(
            stage=stage,
            direction=direction,
            reason="authority_tags_invented",
            t0=t0,
            s_n=s_n_f,
            write_scope=write_scope,
            packet_digest=digest,
            forbidden_keys=tuple(forbidden),
            detail=f"forbidden_keys={forbidden}",
            mouth_contract=mouth,
        )

    # Nested authority objects / invented authority plane claims.
    nested_auth = uml_resolved.get("authority")
    if nested_auth is not None:
        return _deny(
            stage=stage,
            direction=direction,
            reason="authority_tags_invented",
            t0=t0,
            s_n=s_n_f,
            write_scope=write_scope,
            packet_digest=digest,
            forbidden_keys=("authority",),
            detail="nested_authority_block",
            mouth_contract=mouth,
        )

    src = uml_resolved.get("source")
    if src is not None:
        src_s = str(src)
        if _source_class(src_s) == "gpu":
            return _deny(
                stage=stage,
                direction=direction,
                reason="gpu_minted_resolved_rejected",
                t0=t0,
                s_n=s_n_f,
                write_scope=write_scope,
                packet_digest=digest,
                detail=f"uml_resolved_source={src_s}",
                mouth_contract=mouth,
            )
        if src_s in {"security", "security_core", "membrane"}:
            return _deny(
                stage=stage,
                direction=direction,
                reason="authority_tags_invented",
                t0=t0,
                s_n=s_n_f,
                write_scope=write_scope,
                packet_digest=digest,
                forbidden_keys=("source",),
                detail=f"uml_resolved_source={src_s}",
                mouth_contract=mouth,
            )

    # Write-scope proof: attaching uml_resolved must not alter opaque fields.
    probe = copy.deepcopy(dict(packet))
    before_opaque = _sha(_opaque_for_digest(probe))
    probe["uml_resolved"] = copy.deepcopy(dict(uml_resolved))
    after_opaque = _sha(_opaque_for_digest(probe))
    if before_opaque != after_opaque:
        return _deny(
            stage=stage,
            direction=direction,
            reason="write_scope_violation",
            t0=t0,
            s_n=s_n_f,
            write_scope=write_scope,
            packet_digest=digest,
            detail="opaque fields changed when attaching uml_resolved",
            mouth_contract=mouth,
        )

    # Mouth contract: resolve payload must not look like a render envelope.
    if mouth.get("present") and (
        "claims" in uml_resolved or "decision_digest" in uml_resolved
    ):
        return _deny(
            stage=stage,
            direction=direction,
            reason="mouth_envelope_invented",
            t0=t0,
            s_n=s_n_f,
            write_scope=write_scope,
            packet_digest=digest,
            detail="uml_resolved must not carry mouth render envelope fields",
            mouth_contract=mouth,
        )

    membrane: dict[str, Any] | None = None
    if consult_membrane:
        egress_text = json.dumps(
            dict(uml_resolved), sort_keys=True, separators=(",", ":")
        )
        membrane = _consult_membrane(stage="OUT", text=egress_text, s_n=s_n_f)
        if membrane.get("consulted") and not membrane.get("allowed", False):
            return _deny(
                stage=stage,
                direction=direction,
                reason="membrane_denied",
                t0=t0,
                s_n=s_n_f,
                write_scope=write_scope,
                packet_digest=digest,
                detail=str(membrane.get("reason") or "security_out_blocked"),
                membrane=membrane,
                mouth_contract=mouth,
            )

    return _allow(
        stage=stage,
        direction=direction,
        reason="uml_resolved_only",
        t0=t0,
        s_n=s_n_f,
        may_invoke_uml=False,
        write_scope=write_scope,
        packet_digest=digest,
        detail="write-back admitted: uml_resolved only; no authority tags",
        membrane=membrane,
        mouth_contract=mouth,
    )


# Aliases for canary/bridge importers that prefer verb nouns.
gate_in = security_in
gate_out = security_out


__all__ = [
    "SCHEMA_VERSION",
    "WRITE_SCOPE",
    "CPU_SOURCES",
    "GPU_SOURCES",
    "FORBIDDEN_AUTHORITY_KEYS",
    "GateReceipt",
    "security_in",
    "security_out",
    "gate_in",
    "gate_out",
]
