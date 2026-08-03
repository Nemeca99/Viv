"""Security-wrapped AIOS Triad kernel.

This module is deliberately dependency-light at import time.  Every governed
AIOS package may reference it without importing the three CLI pillars during
module initialization.  RID, AUTO, UML, and the Rust membrane are loaded only
when a request opens a context.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping
import uuid


TRIAD_CONTRACT_VERSION = "viv_triad_contract_v1"
FOUNDATION_ROOT = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION_ROOT.parent
TRIAD_ROOT = FOUNDATION_ROOT / "artifacts" / "auto" / "triad"
TRIAD_LEDGER = TRIAD_ROOT / "triad_receipts.jsonl"
TRIAD_LOCK = TRIAD_ROOT / ".triad_receipts.lock"
DEFAULT_CONTEXT_TTL_S = 300.0
PILLAR_MODULES = {
    "rid": "rid_main",
    "auto": "auto_main",
    "uml": "uml_main",
}
_ACTIVE_CONTEXTS: dict[str, str] = {}


class TriadError(RuntimeError):
    """Base class for deterministic Triad failures."""


class TriadDenied(TriadError):
    """Raised when Security or one of the three pillars denies a request."""

    def __init__(self, reason: str, *, evidence: Mapping[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.evidence = dict(evidence or {})


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _sha256(value: Any) -> str:
    raw = value if isinstance(value, bytes) else _stable_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _finite_s_n(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TriadDenied("invalid_s_n", evidence={"value": value}) from exc
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise TriadDenied("invalid_s_n", evidence={"value": value})
    return result


@dataclass(frozen=True)
class TriadEnvelope:
    trace_id: str
    actor: str
    source: str
    target: str
    action: str
    payload: Any
    payload_sha256: str
    s_n: float
    contract_version: str
    created_at: str

    @classmethod
    def build(
        cls,
        *,
        actor: str,
        source: str,
        target: str,
        action: str,
        payload: Any,
        s_n: float,
        trace_id: str | None = None,
    ) -> "TriadEnvelope":
        if not all(str(value).strip() for value in (actor, source, target, action)):
            raise TriadDenied("missing_envelope_identity")
        normalized_s_n = _finite_s_n(s_n)
        return cls(
            trace_id=trace_id or uuid.uuid4().hex,
            actor=str(actor).strip(),
            source=str(source).strip(),
            target=str(target).strip(),
            action=str(action).strip().upper(),
            payload=payload,
            payload_sha256=_sha256(payload),
            s_n=normalized_s_n,
            contract_version=TRIAD_CONTRACT_VERSION,
            created_at=_utc(),
        )

    @classmethod
    def from_value(cls, value: "TriadEnvelope | Mapping[str, Any]") -> "TriadEnvelope":
        if isinstance(value, cls):
            envelope = value
        else:
            raw = dict(value)
            envelope = cls(
                trace_id=str(raw.get("trace_id") or ""),
                actor=str(raw.get("actor") or ""),
                source=str(raw.get("source") or ""),
                target=str(raw.get("target") or ""),
                action=str(raw.get("action") or "").upper(),
                payload=raw.get("payload"),
                payload_sha256=str(raw.get("payload_sha256") or ""),
                s_n=_finite_s_n(raw.get("s_n")),
                contract_version=str(raw.get("contract_version") or ""),
                created_at=str(raw.get("created_at") or ""),
            )
        envelope.validate()
        return envelope

    def validate(self) -> None:
        if self.contract_version != TRIAD_CONTRACT_VERSION:
            raise TriadDenied(
                "triad_contract_version_mismatch",
                evidence={
                    "expected": TRIAD_CONTRACT_VERSION,
                    "actual": self.contract_version,
                },
            )
        if not all(
            str(value).strip()
            for value in (self.trace_id, self.actor, self.source, self.target, self.action)
        ):
            raise TriadDenied("malformed_envelope")
        _finite_s_n(self.s_n)
        if self.payload_sha256 != _sha256(self.payload):
            raise TriadDenied("payload_hash_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TriadContext:
    context_id: str
    envelope: TriadEnvelope
    opened_at: str
    expires_monotonic: float
    security_ingress: dict[str, Any]
    rid: dict[str, Any]
    auto: dict[str, Any]
    uml: dict[str, Any]
    pillar_versions: dict[str, str]

    def validate(self) -> None:
        self.envelope.validate()
        if time.monotonic() > self.expires_monotonic:
            raise TriadDenied("triad_context_expired", evidence={"context_id": self.context_id})
        if not self.security_ingress.get("allowed"):
            raise TriadDenied("security_ingress_denied", evidence=self.security_ingress)
        for name, verdict in (("rid", self.rid), ("auto", self.auto), ("uml", self.uml)):
            if not verdict.get("allowed", verdict.get("ok", False)):
                raise TriadDenied(f"{name}_pillar_denied", evidence=verdict)
        active = _ACTIVE_CONTEXTS.get(self.context_id)
        if active is None or active != _context_binding(self):
            raise TriadDenied(
                "triad_context_authenticity_failed",
                evidence={"context_id": self.context_id},
            )
        current_versions = {
            name: str(module.triad_descriptor().get("version") or "")
            for name, module in _load_pillars().items()
        }
        if current_versions != self.pillar_versions:
            raise TriadDenied(
                "triad_pillar_version_changed",
                evidence={"opened": self.pillar_versions, "current": current_versions},
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["envelope"] = self.envelope.to_dict()
        return payload


@dataclass(frozen=True)
class TriadReceipt:
    receipt_id: str
    trace_id: str
    context_id: str
    stage: str
    allowed: bool
    reason: str
    input_sha256: str
    output_sha256: str | None
    security: dict[str, Any]
    pillars: dict[str, Any]
    created_at: str
    ledger_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _security_module():
    return importlib.import_module("lib.security_membrane")


def _load_pillars() -> dict[str, Any]:
    modules: dict[str, Any] = {}
    for name, module_name in PILLAR_MODULES.items():
        module = importlib.import_module(module_name)
        descriptor_fn = getattr(module, "triad_descriptor", None)
        if descriptor_fn is None:
            raise TriadDenied(
                "pillar_contract_missing",
                evidence={"pillar": name, "module": module_name},
            )
        descriptor = dict(descriptor_fn())
        if descriptor.get("triad_contract_version") != TRIAD_CONTRACT_VERSION:
            raise TriadDenied(
                "pillar_contract_version_mismatch",
                evidence={"pillar": name, "descriptor": descriptor},
            )
        modules[name] = module
    return modules


def _acquire_lock(timeout_s: float = 5.0) -> int:
    TRIAD_ROOT.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            return os.open(TRIAD_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TriadError("triad_ledger_lock_timeout")
            time.sleep(0.025)


def _release_lock(fd: int) -> None:
    try:
        os.close(fd)
    finally:
        TRIAD_LOCK.unlink(missing_ok=True)


def _last_ledger_hash() -> str:
    if not TRIAD_LEDGER.is_file():
        return "0" * 64
    last = ""
    with TRIAD_LEDGER.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last = line
    if not last:
        return "0" * 64
    try:
        return str(json.loads(last).get("ledger_hash") or "0" * 64)
    except json.JSONDecodeError as exc:
        raise TriadError("triad_ledger_malformed") from exc


def _append_receipt(receipt: TriadReceipt, *, s_n: float) -> TriadReceipt:
    security = _security_module()
    base = receipt.to_dict()
    base.pop("ledger_hash", None)
    encoded = _stable_json(base)
    gate = security.tool_gate(
        "write_file",
        {
            "path": str(TRIAD_LEDGER).replace("\\", "/"),
            "content_sha256": _sha256(encoded.encode("utf-8")),
            "bytes": len(encoded.encode("utf-8")),
        },
        s_n,
        forensic_buffer="AIOS Triad receipt append",
    )
    if not gate.get("allowed"):
        raise TriadDenied("triad_ledger_write_denied", evidence=gate)
    fd = _acquire_lock()
    try:
        previous = _last_ledger_hash()
        ledger_hash = _sha256({"previous_hash": previous, "receipt": base})
        row = {**base, "previous_hash": previous, "ledger_hash": ledger_hash}
        TRIAD_ROOT.mkdir(parents=True, exist_ok=True)
        with TRIAD_LEDGER.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_stable_json(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        _release_lock(fd)
    return TriadReceipt(**{**base, "ledger_hash": ledger_hash})


def _receipt(
    context: TriadContext,
    *,
    stage: str,
    allowed: bool,
    reason: str,
    input_value: Any,
    output_value: Any = None,
    security: Mapping[str, Any] | None = None,
    pillars: Mapping[str, Any] | None = None,
) -> TriadReceipt:
    receipt = TriadReceipt(
        receipt_id=uuid.uuid4().hex,
        trace_id=context.envelope.trace_id,
        context_id=context.context_id,
        stage=stage,
        allowed=bool(allowed),
        reason=str(reason),
        input_sha256=_sha256(input_value),
        output_sha256=_sha256(output_value) if output_value is not None else None,
        security=dict(security or {}),
        pillars=dict(pillars or {}),
        created_at=_utc(),
    )
    return _append_receipt(receipt, s_n=context.envelope.s_n)


def _context_binding(context: TriadContext) -> str:
    return _sha256(
        {
            "context_id": context.context_id,
            "envelope": context.envelope.to_dict(),
            "opened_at": context.opened_at,
            "security_ingress": context.security_ingress,
            "rid": context.rid,
            "auto": context.auto,
            "uml": context.uml,
            "pillar_versions": context.pillar_versions,
        }
    )


def open_context(
    envelope: TriadEnvelope | Mapping[str, Any],
    *,
    ttl_s: float = DEFAULT_CONTEXT_TTL_S,
) -> TriadContext:
    """Open one fail-closed Security -> RID/AUTO/UML request context."""
    env = TriadEnvelope.from_value(envelope)
    if not math.isfinite(float(ttl_s)) or not 0.0 < float(ttl_s) <= 3600.0:
        raise TriadDenied("invalid_context_ttl")
    security = _security_module()
    membrane_halt = security.require_membrane()
    if membrane_halt:
        raise TriadDenied("security_membrane_unavailable", evidence=membrane_halt)
    raw = _stable_json(env.to_dict())
    ingress = dict(security.ingress_gate(raw, env.s_n))
    if not ingress.get("allowed"):
        raise TriadDenied("security_ingress_denied", evidence=ingress)

    pillars = _load_pillars()
    uml = dict(pillars["uml"].triad_validate_envelope(env.to_dict()))
    rid = dict(pillars["rid"].triad_observe(env.to_dict()))
    auto = dict(pillars["auto"].triad_decide(env.to_dict(), rid=rid, uml=uml))
    versions = {
        name: str(module.triad_descriptor().get("version") or "")
        for name, module in pillars.items()
    }
    context = TriadContext(
        context_id=uuid.uuid4().hex,
        envelope=env,
        opened_at=_utc(),
        expires_monotonic=time.monotonic() + float(ttl_s),
        security_ingress=ingress,
        rid=rid,
        auto=auto,
        uml=uml,
        pillar_versions=versions,
    )
    _ACTIVE_CONTEXTS[context.context_id] = _context_binding(context)
    context.validate()
    _receipt(
        context,
        stage="OPEN",
        allowed=True,
        reason="security_and_triad_allowed",
        input_value=env.to_dict(),
        security=ingress,
        pillars={"rid": rid, "auto": auto, "uml": uml},
    )
    return context


def authorize_operation(
    context: TriadContext,
    *,
    operation: str,
    params: Mapping[str, Any],
    tool_name: str | None = None,
) -> TriadReceipt:
    """Authorize one internal or external operation within an open context."""
    context.validate()
    pillars = _load_pillars()
    structural = dict(
        pillars["uml"].triad_validate_operation(
            operation=str(operation),
            params=dict(params),
            context=context.to_dict(),
        )
    )
    policy = dict(
        pillars["auto"].triad_authorize_capability(
            operation=str(operation),
            params=dict(params),
            context=context.to_dict(),
            uml=structural,
        )
    )
    security_verdict: dict[str, Any] = {"allowed": True, "stage": "internal"}
    if tool_name:
        security_verdict = dict(
            _security_module().tool_gate(
                str(tool_name),
                dict(params),
                context.envelope.s_n,
                forensic_buffer=f"Triad operation {operation}",
                raw_input=_stable_json(context.envelope.to_dict()),
            )
        )
    allowed = bool(structural.get("allowed")) and bool(policy.get("allowed")) and bool(
        security_verdict.get("allowed")
    )
    if allowed:
        reason = "authorized"
    elif not structural.get("allowed"):
        reason = str(structural.get("reason") or "uml_operation_denied")
    elif not policy.get("allowed"):
        reason = str(policy.get("reason") or "auto_operation_denied")
    else:
        reason = str(security_verdict.get("reason") or "security_operation_denied")
    receipt = _receipt(
        context,
        stage="DISPATCH",
        allowed=allowed,
        reason=reason,
        input_value={"operation": operation, "params": dict(params)},
        security=security_verdict,
        pillars={"auto": policy, "uml": structural, "rid": context.rid},
    )
    if not allowed:
        raise TriadDenied(reason, evidence=receipt.to_dict())
    return receipt


def dispatch(
    context: TriadContext,
    *,
    operation: str,
    params: Mapping[str, Any],
    handler: Callable[[], Any],
    tool_name: str | None = None,
) -> tuple[Any, TriadReceipt]:
    """Authorize, execute, and receipt one bounded operation."""
    authorize_operation(
        context,
        operation=operation,
        params=params,
        tool_name=tool_name,
    )
    try:
        result = handler()
    except Exception as exc:
        _receipt(
            context,
            stage="EXECUTE",
            allowed=False,
            reason=f"{type(exc).__name__}:{exc}",
            input_value={"operation": operation, "params": dict(params)},
        )
        raise
    receipt = _receipt(
        context,
        stage="EXECUTE",
        allowed=True,
        reason="executed",
        input_value={"operation": operation, "params": dict(params)},
        output_value=result,
    )
    return result, receipt


def emit(context: TriadContext, result: Any) -> tuple[Any, TriadReceipt]:
    """Pass a result back through UML/AUTO/RID and Security OUT."""
    context.validate()
    pillars = _load_pillars()
    structural = dict(
        pillars["uml"].triad_validate_result(result=result, context=context.to_dict())
    )
    policy = dict(
        pillars["auto"].triad_authorize_egress(
            result=result,
            context=context.to_dict(),
            uml=structural,
        )
    )
    if not structural.get("allowed") or not policy.get("allowed"):
        reason = str(structural.get("reason") or policy.get("reason") or "pillar_egress_denied")
        raise TriadDenied(reason, evidence={"uml": structural, "auto": policy})
    text = result if isinstance(result, str) else _stable_json(result)
    filtered, security_verdict = _security_module().filter_egress(
        text, context.envelope.s_n
    )
    security_result = dict(security_verdict or {"allowed": True, "stage": "empty"})
    allowed = bool(security_result.get("allowed", filtered is not None))
    receipt = _receipt(
        context,
        stage="EMIT",
        allowed=allowed,
        reason="emitted" if allowed else str(security_result.get("reason") or "egress_denied"),
        input_value=result,
        output_value=filtered,
        security=security_result,
        pillars={"rid": context.rid, "auto": policy, "uml": structural},
    )
    if not allowed:
        raise TriadDenied("security_egress_denied", evidence=receipt.to_dict())
    return filtered, receipt


def verify_triad_ledger() -> dict[str, Any]:
    previous = "0" * 64
    events = 0
    if not TRIAD_LEDGER.is_file():
        return {"ok": True, "events": 0, "head": previous, "path": str(TRIAD_LEDGER)}
    with TRIAD_LEDGER.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                return {"ok": False, "line": number, "reason": f"malformed:{exc}"}
            ledger_hash = str(row.pop("ledger_hash", ""))
            row_previous = str(row.pop("previous_hash", ""))
            expected = _sha256({"previous_hash": previous, "receipt": row})
            if row_previous != previous or ledger_hash != expected:
                return {"ok": False, "line": number, "reason": "hash_chain_mismatch"}
            previous = ledger_hash
            events += 1
    return {
        "ok": True,
        "events": events,
        "head": previous,
        "path": str(TRIAD_LEDGER),
    }


def triad_status() -> dict[str, Any]:
    try:
        pillars = _load_pillars()
        descriptors = {name: module.triad_descriptor() for name, module in pillars.items()}
        error = None
    except Exception as exc:  # status reports; operations still fail closed
        descriptors = {}
        error = f"{type(exc).__name__}:{exc}"
    return {
        "contract_version": TRIAD_CONTRACT_VERSION,
        "pillars": descriptors,
        "ledger": verify_triad_ledger(),
        "error": error,
    }
