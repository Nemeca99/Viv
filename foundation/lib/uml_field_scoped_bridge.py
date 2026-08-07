"""Field-scoped identity→UML bridge (canary boundary).

Binding path:
  identity packet.uml_request → Security IN → seal destination →
  UML decide_route → Security OUT → write uml_resolved only

Invariants:
  - Explicit uml_request only (no prose / SCAN_SURFACE fallback)
  - Destination seal precedes route choice
  - Opaque identity/context fields byte-equivalent
  - Ambiguity / unbound / invented binding → HOLD / fail-closed
  - Security remains an external authority plane; bridge never mints it
  - Canary-only: caller must pass canary_enabled=True (operator gate)
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Mapping

from lib.uml_equation_registry import UMLEquationRegistry, _domains_in_expr
from lib.uml_route_governor import decide_route, route_efficiency_error

SCHEMA_VERSION = "uml_field_scoped_bridge_v1"
BRIDGE_MODE = "FIELD_SCOPED_CANARY"
CANARY_ENV = "FIELD_SCOPED_BRIDGE_CANARY"

_CPU_SOURCES = frozenset({"cpu", "cpu_identity", "cpu_authority", "operator"})

# Specific deny classes Security IN/OUT may emit that must surface at
# BridgeInvokeResult.reason_class (do not collapse to security_*_denied).
# Keeps fail-closed; only improves receipt taxonomy for known classes.
_SURFACED_GATE_DENY_REASONS = frozenset(
    {
        "invented_binding",
        "authority_violation",
        "authority_tags_invented",
        "gpu_minted_rejected",
        "gpu_minted_resolved_rejected",
        "ambiguous_packet",
        "ambiguous_uml_request",
        "ambiguous_request_kind",
        "ambiguous_request_kind_type",
        "ambiguous_or_missing",
        "ambiguous_or_missing_destination",
        "ambiguous_target_char",
        "ambiguous_target_value",
        "ambiguous_uml_resolved",
        "missing_uml_resolved",
        "missing_uml_request",
        "uml_request_not_mapping",
        "seal_failed",
        "write_scope_violation",
        "mouth_envelope_invented",
        "destination_mismatch",
        "unknown_char",
        "unknown_value",
        "missing_destination",
        "unsupported_request_kind",
    }
)


def _surface_gate_deny_reason(fallback: str, gate_reason: str | None) -> str:
    """Promote known security_in/out.reason values to top-level reason_class."""
    raw = str(gate_reason or "").strip()
    if not raw:
        return fallback
    if raw in _SURFACED_GATE_DENY_REASONS:
        return raw
    # Gate may emit unsupported_request_kind:<kind>
    if raw.startswith("unsupported_request_kind"):
        return "unsupported_request_kind"
    return fallback


class BridgeError(Exception):
    def __init__(self, reason_class: str, detail: str):
        super().__init__(detail)
        self.reason_class = reason_class
        self.detail = detail


def _sha(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _federation(expr: str) -> str:
    domains = sorted(_domains_in_expr(expr))
    return "".join(domains) if domains else "LIT"


def security_gate(
    *,
    stage: str,
    text: str,
    s_n: float,
) -> dict[str, Any]:
    """Legacy text membrane consult (kept for callers). Prefer packet gates.

    Packet-scoped API lives in ``lib.uml_bridge_security_gate``:
    ``security_in(packet)`` / ``security_out(packet, uml_resolved)``.
    Bridge does not mint Security authority.
    """
    stage = str(stage).upper()
    try:
        from lib.security_membrane import egress_gate, ingress_gate
        from lib.security_bridge import rust_available, rust_error
    except Exception as exc:
        return {
            "allowed": False,
            "stage": f"security_{stage.lower()}",
            "direction": stage,
            "reason": "security_import_failed",
            "security_plane": "external",
            "authority_minted": False,
            "detail": repr(exc),
            "s_n": float(s_n),
        }

    if not rust_available():
        return {
            "allowed": False,
            "stage": f"security_{stage.lower()}",
            "direction": stage,
            "reason": f"security_core_unavailable:{rust_error()}",
            "security_plane": "external",
            "authority_minted": False,
            "s_n": float(s_n),
        }

    if stage == "IN":
        verdict = dict(ingress_gate(str(text), float(s_n)))
    elif stage == "OUT":
        verdict = dict(egress_gate(str(text), float(s_n)))
    else:
        return {
            "allowed": False,
            "stage": "security_unknown",
            "direction": stage,
            "reason": "unknown_security_stage",
            "security_plane": "external",
            "authority_minted": False,
            "s_n": float(s_n),
        }
    verdict["security_plane"] = "external"
    verdict["authority_minted"] = False
    return verdict


def assert_cpu_authority(uml_request: Mapping[str, Any] | None) -> None:
    if not uml_request:
        return
    source = str(uml_request.get("source") or "cpu")
    if source not in _CPU_SOURCES:
        raise BridgeError("authority_violation", f"uml_request_source={source}")


def resolve_sealed_destination(
    registry: UMLEquationRegistry, uml_request: Mapping[str, Any]
) -> tuple[str, int]:
    """Seal destination before any route choice. Fail-closed on ambiguity."""
    kind = str(uml_request.get("request_kind") or "")
    if kind == "invented_binding":
        raise BridgeError("invented_binding", "structure_without_sealed_binding")
    if kind != "sealed_destination":
        raise BridgeError("unsupported_request_kind", kind or "missing")

    ch = uml_request.get("target_char")
    val = uml_request.get("target_value")
    if ch is not None:
        ch = str(ch)
        if ch not in registry.entries:
            raise BridgeError("unknown_char", repr(ch))
        sealed_val = int(registry.entries[ch]["token_id"])
        if val is not None and int(val) != sealed_val:
            raise BridgeError(
                "destination_mismatch",
                f"char={ch!r} sealed={sealed_val} claimed={val}",
            )
        return ch, sealed_val
    if val is not None:
        sealed_val = int(val)
        if sealed_val not in registry.value_to_char:
            raise BridgeError("unknown_value", str(sealed_val))
        return str(registry.value_to_char[sealed_val]), sealed_val
    raise BridgeError("missing_destination", "no target_char/target_value")


def is_intent_packet(obj: Mapping[str, Any]) -> bool:
    """True for CPU intent packets (tagged) vs shadow identity shells."""
    return isinstance(obj, Mapping) and (
        "tagged_packet" in obj or (obj.get("version") is not None and "facts" in obj)
    )


def _opaque_view(surface: Mapping[str, Any]) -> dict[str, Any]:
    """Everything except uml_resolved (write scope)."""
    return {k: v for k, v in surface.items() if k != "uml_resolved"}


def _extract_uml_request(surface: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Field-scoped ingress: packet['uml_request'] only — never prose/scan."""
    req = surface.get("uml_request")
    if req is None:
        return None
    if not isinstance(req, Mapping):
        raise BridgeError("uml_request_not_mapping", type(req).__name__)
    return req


@dataclass
class BridgeInvokeResult:
    status: str
    fail_closed: bool
    reason_class: str | None
    detail: str | None
    canary_enabled: bool
    uml_invoked: bool
    identity_out: dict[str, Any]
    identity_payload_sha_before: str
    identity_opaque_sha_after: str
    security_in: dict[str, Any] | None
    security_out: dict[str, Any] | None
    target_char: str | None = None
    target_value: int | None = None
    selected_route: str | None = None
    decoded_char: str | None = None
    domains: list[str] | None = None
    federation: str | None = None
    selected_cost: int | None = None
    route_kind: str | None = None
    destination_match: bool = False
    elapsed_ms: float = 0.0
    authority_leak: bool = False
    ingress_surface: str = "identity_shell"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "bridge_mode": BRIDGE_MODE,
            "status": self.status,
            "fail_closed": self.fail_closed,
            "reason_class": self.reason_class,
            "detail": self.detail,
            "canary_enabled": self.canary_enabled,
            "uml_invoked": self.uml_invoked,
            "ingress_surface": self.ingress_surface,
            "default_path": False,
            "promotion": False,
            "scan_surface": False,
            "target_char": self.target_char,
            "target_value": self.target_value,
            "selected_route": self.selected_route,
            "decoded_char": self.decoded_char,
            "domains": self.domains,
            "federation": self.federation,
            "selected_cost": self.selected_cost,
            "route_kind": self.route_kind,
            "destination_match": self.destination_match,
            "identity_payload_sha_before": self.identity_payload_sha_before,
            "identity_opaque_sha_after": self.identity_opaque_sha_after,
            "identity_out": self.identity_out,
            "security_in": self.security_in,
            "security_out": self.security_out,
            "authority_leak": self.authority_leak,
            "elapsed_ms": self.elapsed_ms,
        }


def invoke_field_scoped_bridge(
    receipt_or_packet: Mapping[str, Any],
    registry: UMLEquationRegistry,
    *,
    canary_enabled: bool,
    s_n: float = 0.95,
) -> BridgeInvokeResult:
    """Invoke field-scoped bridge. UML runs only when canary_enabled and sealed.

    Ingress: read ``surface['uml_request']`` only (intent packet or shell).
    Egress write-back: ``attach_uml_resolved`` for intent packets; else
    ``identity_payload['uml_resolved']`` / shell ``uml_resolved`` only.

    When canary_enabled is False: no UML side effects (rollback / disabled path).
    """
    t0 = time.perf_counter()
    packet_mode = is_intent_packet(receipt_or_packet)
    ingress_surface = "intent_packet" if packet_mode else "identity_shell"

    if packet_mode:
        working = copy.deepcopy(dict(receipt_or_packet))
        opaque_before = _opaque_view(working)
    else:
        # Shadow shell: opaque = identity_payload; uml_request is sibling field.
        working = {
            "identity_payload": copy.deepcopy(
                dict(receipt_or_packet.get("identity_payload") or {})
            ),
            "uml_request": copy.deepcopy(receipt_or_packet.get("uml_request"))
            if receipt_or_packet.get("uml_request") is not None
            else None,
        }
        opaque_before = copy.deepcopy(working["identity_payload"])

    identity_sha_before = _sha(opaque_before)

    if not canary_enabled:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        out = working if packet_mode else working["identity_payload"]
        return BridgeInvokeResult(
            status="DISABLED",
            fail_closed=True,
            reason_class="canary_disabled",
            detail="FIELD_SCOPED_BRIDGE_CANARY off — no UML invocation",
            canary_enabled=False,
            uml_invoked=False,
            identity_out=out,
            identity_payload_sha_before=identity_sha_before,
            identity_opaque_sha_after=identity_sha_before,
            security_in=None,
            security_out=None,
            elapsed_ms=elapsed_ms,
            ingress_surface=ingress_surface,
        )

    security_in: dict[str, Any] | None = None
    security_out: dict[str, Any] | None = None
    try:
        from lib.uml_bridge_security_gate import (
            security_in as packet_security_in,
            security_out as packet_security_out,
        )

        # Security IN wraps UML invoke — packet gate before destination seal.
        in_receipt = packet_security_in(working, s_n=s_n)
        security_in = in_receipt.to_dict()
        if not in_receipt.allowed:
            gate_reason = str(in_receipt.reason or "")
            raise BridgeError(
                _surface_gate_deny_reason("security_in_denied", gate_reason),
                str(in_receipt.detail or gate_reason or "security_in_blocked"),
            )
        if not in_receipt.may_invoke_uml:
            raise BridgeError("missing_uml_request", "uml_request required")

        uml_request = _extract_uml_request(working)
        if not uml_request:
            raise BridgeError("missing_uml_request", "uml_request required")

        assert_cpu_authority(uml_request)

        # Destination seal BEFORE route choice (after Security IN admit).
        target_char, target_value = resolve_sealed_destination(registry, uml_request)

        proposals = uml_request.get("proposals")
        decision = decide_route(
            registry,
            target_char=target_char,
            target_value=target_value,
            proposals=list(proposals) if proposals else None,
            include_registry_pool=True,
            policy=str(uml_request.get("prefer_policy") or "cheapest_valid"),
        )
        selected = str(decision.selected)
        decoded = registry.decode_eq(selected)
        if decoded != target_char:
            raise BridgeError(
                "seal_break",
                f"decoded={decoded!r} sealed={target_char!r}",
            )
        eff = route_efficiency_error(
            registry, proposed=selected, target_char=target_char
        )
        domains = sorted(_domains_in_expr(selected))
        federation = _federation(selected)

        uml_resolved = {
            "target_char": target_char,
            "target_value": target_value,
            "selected_route": selected,
            "domains": domains,
            "federation": federation,
            "selected_cost": int(decision.selected_cost),
            "route_kind": eff.get("kind"),
            "bridge_mode": BRIDGE_MODE,
            "canary_only": True,
            "default_path": False,
        }

        # Security OUT before commit — uml_resolved-only write scope.
        out_receipt = packet_security_out(working, uml_resolved, s_n=s_n)
        security_out = out_receipt.to_dict()
        if not out_receipt.allowed:
            gate_reason = str(out_receipt.reason or "")
            raise BridgeError(
                _surface_gate_deny_reason("security_out_denied", gate_reason),
                str(out_receipt.detail or gate_reason or "security_out_blocked"),
            )

        if packet_mode:
            from voice_core.intent_packet import attach_uml_resolved

            attach_uml_resolved(working, uml_resolved)
            opaque_after = _opaque_view(working)
            identity_out = working
        else:
            identity_after = copy.deepcopy(working["identity_payload"])
            identity_after["uml_resolved"] = uml_resolved
            opaque_after = {k: v for k, v in identity_after.items() if k != "uml_resolved"}
            identity_out = identity_after

        opaque_sha = _sha(opaque_after)
        if opaque_sha != identity_sha_before:
            raise BridgeError("identity_payload_mutated", "opaque fields changed")

        authority_leak = bool(
            security_in.get("authority_minted")
            or security_out.get("authority_minted")
            or security_in.get("security_plane") != "external"
            or security_out.get("security_plane") != "external"
        )
        if authority_leak:
            raise BridgeError("authority_leak", "bridge_minted_or_internalized_security")

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return BridgeInvokeResult(
            status="PASS",
            fail_closed=False,
            reason_class=None,
            detail=None,
            canary_enabled=True,
            uml_invoked=True,
            identity_out=identity_out,
            identity_payload_sha_before=identity_sha_before,
            identity_opaque_sha_after=opaque_sha,
            security_in=security_in,
            security_out=security_out,
            target_char=target_char,
            target_value=target_value,
            selected_route=selected,
            decoded_char=decoded,
            domains=domains,
            federation=federation,
            selected_cost=int(decision.selected_cost),
            route_kind=str(eff.get("kind")) if eff.get("kind") is not None else None,
            destination_match=True,
            elapsed_ms=elapsed_ms,
            authority_leak=False,
            ingress_surface=ingress_surface,
        )
    except BridgeError as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        out = working if packet_mode else working["identity_payload"]
        return BridgeInvokeResult(
            status="FAIL_CLOSED",
            fail_closed=True,
            reason_class=exc.reason_class,
            detail=exc.detail,
            canary_enabled=True,
            uml_invoked=False,
            identity_out=out,
            identity_payload_sha_before=identity_sha_before,
            identity_opaque_sha_after=identity_sha_before,
            security_in=security_in,
            security_out=security_out,
            elapsed_ms=elapsed_ms,
            authority_leak=False,
            ingress_surface=ingress_surface,
        )
