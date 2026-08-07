"""Deterministic privacy, consent, retention, and transparency planning."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

MODULE_ID = "privacy_core"
VERSION = "v1"
MANUAL_SECTION = "3.15"
MANUAL_SOURCE = "F:/AIOS_Clean/privacy_core"
DEFAULT_MODE = "semi-auto"
MAX_RETENTION_DAYS = 3650
LEARNING_SOURCES = ("conversation", "explicit_user_input", "passive", "behavior", "predictive")


def _bounded_days(value: Any, default: int = 365) -> int:
    try:
        return max(0, min(int(value), MAX_RETENTION_DAYS))
    except (TypeError, ValueError):
        return default


def normalize_settings(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Normalize supplied settings and fail closed on invalid consent."""
    raw = dict(config or {})
    requested = str(raw.get("mode") or DEFAULT_MODE).casefold()
    consent = raw.get("consent") if isinstance(raw.get("consent"), Mapping) else {}
    learning = raw.get("learning") if isinstance(raw.get("learning"), Mapping) else {}
    retention = raw.get("data_retention") if isinstance(raw.get("data_retention"), Mapping) else {}
    transparency = raw.get("transparency") if isinstance(raw.get("transparency"), Mapping) else {}
    consent_valid = bool(consent.get("full_auto_enabled")) and bool(consent.get("user_acknowledged"))
    full_auto = requested == "full-auto" and consent_valid
    effective = "full-auto" if full_auto else DEFAULT_MODE
    return {
        "ok": True,
        "state": "VERIFIED",
        "requested_mode": requested,
        "mode": effective,
        "mode_was_downgraded": requested == "full-auto" and not full_auto,
        "learning": {
            "conversation_only": True,
            "passive_monitoring": full_auto and bool(learning.get("passive_monitoring")),
            "predictive": full_auto and bool(learning.get("predictive")),
            "always_listening": False,
            "behavior_tracking": full_auto and bool(learning.get("behavior_tracking")),
        },
        "consent": {
            "full_auto_enabled": consent_valid,
            "user_acknowledged": bool(consent.get("user_acknowledged")),
            "explicit_consent_required": True,
            "can_be_disabled_anytime": True,
        },
        "data_retention": {
            "conversations": bool(retention.get("conversations", True)),
            "behavioral_data": full_auto and bool(retention.get("behavioral_data")),
            "max_age_days": _bounded_days(retention.get("max_age_days", 365)),
            "auto_cleanup": bool(retention.get("auto_cleanup", False)),
            "keep_aggregated_stats": bool(retention.get("keep_aggregated_stats", True)),
        },
        "transparency": {
            "show_what_is_learned": bool(transparency.get("show_what_is_learned", True)),
            "allow_data_export": bool(transparency.get("allow_data_export", True)),
            "allow_selective_deletion": bool(transparency.get("allow_selective_deletion", True)),
        },
        "data_stays_local": True,
        "fail_closed": True,
        "writes_performed": False,
        "llm_authority": False,
    }


def plan_mode_change(config: Mapping[str, Any] | None, requested_mode: str, *, explicit_consent: bool = False) -> dict[str, Any]:
    """Propose a reversible mode change without applying configuration."""
    target = str(requested_mode).strip().casefold()
    policy = normalize_settings(config)
    if target == "semi-auto":
        allowed = True
        reason = "restrictive_mode_always_available"
    elif target == "full-auto":
        consent = config.get("consent") if isinstance(config, Mapping) and isinstance(config.get("consent"), Mapping) else {}
        allowed = bool(explicit_consent and consent.get("full_auto_enabled") and consent.get("user_acknowledged"))
        reason = "explicit_consent_verified" if allowed else "explicit_consent_required"
    else:
        allowed = False
        reason = "unknown_mode"
    return {"ok": allowed, "state": "PROPOSED" if allowed else "DENIED", "requested_mode": target, "current_mode": policy["mode"], "reason": reason, "reversible": True, "applied": False, "writes_performed": False, "llm_authority": False}


def authorize_learning(source_kind: str, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    policy = normalize_settings(config)
    source = str(source_kind).strip().casefold()
    allowed = source in {"conversation", "explicit_user_input"} or (policy["mode"] == "full-auto" and source in {"passive", "behavior", "predictive"})
    return {"ok": allowed, "allowed": allowed, "source_kind": source, "known_source": source in LEARNING_SOURCES, "reason": "authorized" if allowed else "consent_required_or_unknown_source", "policy": policy}


def plan_retention(config: Mapping[str, Any] | None = None, *, category: str = "conversations", max_age_days: int | None = None, automatic_cleanup: bool | None = None) -> dict[str, Any]:
    """Prepare retention policy without deleting or changing records."""
    policy = normalize_settings(config)
    chosen_days = _bounded_days(max_age_days if max_age_days is not None else policy["data_retention"]["max_age_days"])
    cleanup = bool(policy["data_retention"]["auto_cleanup"] if automatic_cleanup is None else automatic_cleanup)
    category_name = str(category).strip().casefold()
    allowed = category_name in {"conversations", "behavioral_data", "aggregated_stats"}
    return {"ok": allowed, "state": "PROPOSED" if allowed else "DENIED", "category": category_name, "max_age_days": chosen_days, "automatic_cleanup": cleanup, "delete_performed": False, "applied": False, "reason": "retention_plan_only" if allowed else "unknown_retention_category", "writes_performed": False, "llm_authority": False}


def transparency_report(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Report categories and source kinds from supplied records, not content."""
    categories: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    rows = list(records)[:512]
    for record in rows:
        if not isinstance(record, Mapping):
            continue
        category = str(record.get("category") or "uncategorized").strip().casefold()
        source = str(record.get("source_kind") or "unknown").strip().casefold()
        categories[category] += 1
        sources[source] += 1
    return {"ok": True, "state": "OBSERVED" if rows else "INSUFFICIENT", "records_observed": len(rows), "categories": dict(sorted(categories.items())), "source_kinds": dict(sorted(sources.items())), "raw_content_returned": False, "writes_performed": False, "llm_authority": False}


def plan_data_action(action: str, target: str, *, confirmation: str = "") -> dict[str, Any]:
    """Create export/delete intent; never executes the data action."""
    selected = str(action).strip().casefold()
    target_name = str(target).strip().casefold()
    if selected == "delete_all":
        confirmed = confirmation == "DELETE"
    else:
        confirmed = bool(target_name)
    allowed = selected in {"export", "delete_topic", "delete_range", "delete_all"} and confirmed
    return {"ok": allowed, "state": "PROPOSED" if allowed else "DENIED", "action": selected, "target": target_name, "confirmation_valid": confirmed, "executed": False, "writes_performed": False, "reason": "explicit_confirmation_required" if not allowed else "handoff_requires_governed_executor", "llm_authority": False}


def module_status() -> dict[str, Any]:
    return {"ok": True, "state": "READY", "module": MODULE_ID, "version": VERSION, "manual_section": MANUAL_SECTION, "read_only": True, "fail_closed": True, "full_auto_requires_explicit_consent": True, "writes_performed": False, "llm_authority": False}
