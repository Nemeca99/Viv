"""Fail-closed CPU privacy and consent policy derived from AIOS privacy_core."""
from __future__ import annotations

from typing import Any, Mapping

MANUAL_SOURCE = "F:/AIOS_Clean/privacy_core"
DEFAULT_MODE = "semi-auto"


def evaluate(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Normalize privacy settings without reading or mutating a config file."""
    raw = dict(config or {})
    mode = str(raw.get("mode") or DEFAULT_MODE).casefold()
    if mode not in {"semi-auto", "full-auto"}:
        mode = DEFAULT_MODE
    learning = raw.get("learning") if isinstance(raw.get("learning"), Mapping) else {}
    consent = raw.get("consent") if isinstance(raw.get("consent"), Mapping) else {}
    acknowledged = bool(consent.get("user_acknowledged"))
    enabled = bool(consent.get("full_auto_enabled"))
    full_auto = mode == "full-auto" and acknowledged and enabled
    return {
        "ok": True,
        "mode": "full-auto" if full_auto else DEFAULT_MODE,
        "conversation_learning": True,
        "passive_monitoring": full_auto and bool(learning.get("passive_monitoring")),
        "predictive": full_auto and bool(learning.get("predictive")),
        "always_listening": full_auto and bool(learning.get("always_listening")),
        "behavior_tracking": full_auto and bool(learning.get("behavior_tracking")),
        "consent_valid": full_auto,
        "can_disable": True,
        "fail_closed": True,
        "source": MANUAL_SOURCE,
        "writes_performed": False,
        "llm_authority": False,
    }


def authorize_learning(source_kind: str, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Authorize only conversation learning by default; broader sources need consent."""
    policy = evaluate(config)
    source = str(source_kind).strip().casefold()
    allowed = source in {"conversation", "explicit_user_input"} or (policy["consent_valid"] and source in {"passive", "behavior", "predictive"})
    return {"ok": allowed, "allowed": allowed, "source_kind": source, "reason": "authorized" if allowed else "consent_required", "policy": policy}
