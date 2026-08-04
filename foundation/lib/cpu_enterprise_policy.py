"""Fail-closed CPU policy/audit surface distilled from enterprise_core.

External integrations, administration, exports, and key operations are
classified here but never executed. Existing governed adapters own effects.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

OPERATIONS = frozenset({"read", "audit", "integrate", "admin", "data_export", "key_rotation"})
CONSENT_REQUIRED = frozenset({"integrate", "admin", "data_export", "key_rotation"})


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def evaluate_request(
    operation: Any,
    *,
    explicit_consent: bool = False,
    authority: str = "none",
    payload: Any = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    op = str(operation or "").strip().casefold()
    allowed = op in OPERATIONS and (op not in CONSENT_REQUIRED or (explicit_consent and authority == "architect"))
    reason = "authorized_read_only" if op in {"read", "audit"} and allowed else "explicit_architect_consent_required" if op in CONSENT_REQUIRED else "operation_not_allowlisted"
    return {
        "ok": True,
        "state": "VERIFIED" if allowed else "DENIED",
        "operation": op,
        "allowed": allowed,
        "reason": reason,
        "audit_id": _digest({"operation": op, "payload": payload}),
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "external_effect": False,
        "writes": False,
        "llm": False,
    }


def probe(payload: dict[str, Any]) -> dict[str, Any]:
    result = evaluate_request(
        payload.get("operation"),
        explicit_consent=bool(payload.get("explicit_consent")),
        authority=str(payload.get("authority") or "none"),
        payload=payload.get("payload"),
        timestamp=payload.get("timestamp"),
    )
    result["policy_source"] = "F:/AIOS_Clean/enterprise_core"
    result["effect_authorized"] = False
    return result
