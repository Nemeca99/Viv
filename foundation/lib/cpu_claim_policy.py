"""CPU claim, privacy, and render-surface policy.

This policy is intentionally mechanical.  It does not decide whether a fact
is true semantically; it checks that the upstream typed contract supplied the
required evidence and that internal paths, telemetry, and conflicts do not
cross into the renderer packet.
"""
from __future__ import annotations

import re
from typing import Any


_PATH = re.compile(r"\b[A-Za-z]:[\\/][^\s`\"']+")
_TELEMETRY = ("master s_n", "master_s_n", "rid=", "telemetry", "internal stability")


def _redact(value: str) -> str:
    text = str(value)
    return _PATH.sub("[internal-path-redacted]", text)


def verify_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Verify a typed packet and return a renderer-safe copy."""
    if not isinstance(packet, dict):
        return {"ok": False, "state": "DENIED", "reason": "packet_not_object"}
    if packet.get("state") != "VERIFIED":
        return {"ok": False, "state": "ABSTAIN", "reason": "packet_not_verified"}
    facts = packet.get("facts") or []
    conflicts = packet.get("conflicts") or []
    if conflicts:
        return {"ok": False, "state": "ABSTAIN", "reason": "packet_conflict", "conflicts": conflicts}
    safe_facts: list[dict[str, Any]] = []
    for fact in facts:
        if not isinstance(fact, dict):
            return {"ok": False, "state": "ABSTAIN", "reason": "malformed_fact"}
        source = fact.get("source") or {}
        if not source.get("sha256") or not source.get("root") or not source.get("kind"):
            return {"ok": False, "state": "ABSTAIN", "reason": "fact_missing_provenance"}
        value = str(fact.get("value") or "")
        if not value.strip():
            return {"ok": False, "state": "ABSTAIN", "reason": "empty_fact"}
        if any(marker in value.casefold() for marker in _TELEMETRY):
            return {"ok": False, "state": "ABSTAIN", "reason": "telemetry_in_fact"}
        safe_source = {key: val for key, val in source.items() if key not in {"path"}}
        safe_facts.append({**fact, "value": _redact(value), "source": safe_source})
    safe = {
        "version": packet.get("version"),
        "authority": packet.get("authority"),
        "query": _redact(str(packet.get("query") or "")),
        "state": "VERIFIED",
        "facts": safe_facts,
        "conflicts": [],
        "three_way": packet.get("three_way") or {"state": "PARTIAL", "present_sources": []},
        "render_rule": "Render only supplied verified facts; preserve uncertainty.",
        "internal_paths_exposed": False,
        "telemetry_allowed": False,
        "llm_authority": False,
    }
    return {"ok": True, "state": "VERIFIED", "packet": safe, "fact_count": len(safe_facts), "llm_authority": False}
