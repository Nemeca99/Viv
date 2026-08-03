"""Rust security membrane on the foundation hot path — IN before process, OUT before world."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.security_bridge import (
    check_growth,
    check_egress,
    check_ingress,
    constitution,
    dormancy_threshold,
    enforce_morality,
    rust_available,
    rust_error,
)
try:
    from voice_core.acronym_registry import validate_acronym_usage
except ModuleNotFoundError:  # direct foundation-only test/import path
    import sys

    _viv_root = Path(__file__).resolve().parents[2]
    if str(_viv_root) not in sys.path:
        sys.path.insert(0, str(_viv_root))
    from voice_core.acronym_registry import validate_acronym_usage
from lib.entity_we_contract import decide_entity_output

EVENTS_PATH = AUTO_ARTIFACTS / "security_events.jsonl"
BLOCKED_EGRESS = "[SECURITY OUT] output withheld — laws enforced at metal."


def membrane_status() -> dict[str, Any]:
    st = {
        "armed": rust_available(),
        "rust_error": rust_error(),
        "dormancy_threshold": dormancy_threshold(),
        "events_path": str(EVENTS_PATH),
    }
    if rust_available():
        c = constitution()
        st["version"] = c.get("version")
        st["architect"] = c.get("architect")
        st["laws"] = len(c.get("laws") or [])
        st["primes"] = len(c.get("primes") or [])
        st["integrity"] = c.get("integrity")
    return st


def tool_gate(
    tool_name: str,
    params: dict[str, Any] | str,
    s_n: float,
    forensic_buffer: str = "",
    raw_input: str = "",
) -> dict[str, Any]:
    """Rust enforce_morality for agentic tool actions — fail-closed."""
    verdict = enforce_morality(tool_name, params, s_n, forensic_buffer, raw_input)
    if not verdict.get("allowed"):
        log_event("tool_blocked", verdict, tool=tool_name)
    return verdict


def growth_gate(actuator: str, proposed_r: float, max_r: float) -> dict[str, Any]:
    """Rust growth-ceiling check through the canonical Python membrane."""
    verdict = check_growth(str(actuator), float(proposed_r), float(max_r))
    if verdict is None:
        result = {
            "allowed": False,
            "reason": "Rust growth API unavailable",
            "law": "membrane",
        }
        log_event("growth_blocked", result, actuator=actuator)
        return result
    result = dict(verdict)
    if not result.get("allowed"):
        log_event("growth_blocked", result, actuator=actuator)
    return result


def require_membrane() -> dict[str, Any] | None:
    """Fail-closed halt payload when Rust membrane is not installed."""
    if rust_available():
        return None
    return {
        "allowed": False,
        "stage": "security_membrane",
        "reason": f"Rust security_core unavailable: {rust_error()}",
        "direction": "IN",
    }


def ingress_gate(text: str, s_n: float) -> dict[str, Any]:
    return dict(check_ingress(text, float(s_n)))


def egress_gate(text: str, s_n: float) -> dict[str, Any]:
    return dict(check_egress(text, float(s_n)))


def filter_egress(text: str | None, s_n: float) -> tuple[str | None, dict[str, Any] | None]:
    if text is None or not str(text).strip():
        return text, None
    acronym_violations = validate_acronym_usage(str(text))
    if acronym_violations:
        verdict = {
            "allowed": False,
            "stage": "security_out",
            "reason": "acronym_contract_violation",
            "acronym_contract": {
                "pass": False,
                "violations": acronym_violations,
            },
        }
        log_event("egress_blocked", verdict, text=str(text)[:500])
        return BLOCKED_EGRESS, verdict
    entity_decision = decide_entity_output(str(text))
    if entity_decision["decision"] != "ACCEPT":
        verdict = {
            "allowed": False,
            "stage": "security_out",
            "reason": f"entity_contract_{entity_decision['decision'].lower()}",
            "entity_contract": entity_decision,
        }
        log_event("egress_blocked", verdict, text=str(text)[:500])
        return BLOCKED_EGRESS, verdict
    verdict = egress_gate(str(text), s_n)
    if verdict.get("allowed"):
        return str(text), verdict
    log_event("egress_blocked", verdict, text=str(text)[:500])
    return BLOCKED_EGRESS, verdict


def log_event(kind: str, verdict: dict[str, Any], **extra: Any) -> None:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "verdict": verdict,
        **extra,
    }
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def heartbeat_stamp(s_n: float) -> dict[str, Any]:
    st = membrane_status()
    st["s_n"] = s_n
    st["ingress"] = "armed" if st["armed"] else "missing"
    st["egress"] = "armed" if st["armed"] else "missing"
    return st
