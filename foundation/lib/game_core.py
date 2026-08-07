"""Effect-closed personal game analytics for the CPU foundation.

The legacy game core combines session persistence, event logging, personal
analytics, and coaching.  This module keeps the deterministic analytics and
coaching decisions while requiring callers to supply session records.  It
does not read or write session files, consult a clock, compare the user with
other people, execute game actions, or call a model.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

MODULE_ID = "game_core"
VERSION = "v1"
MANUAL_SECTION = "3.12"
MANUAL_SOURCE = "F:/AIOS_Clean/game_core"
MAX_SESSIONS = 128
MAX_EVENTS = 256
MAX_TEXT = 300


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())[:MAX_TEXT]


def _hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _data(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = event.get("data")
    return value if isinstance(value, Mapping) else {}


def validate_session(session: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one caller-supplied session without opening a path."""
    if not isinstance(session, Mapping):
        return {"ok": False, "state": "ABSTAIN", "reason": "session_not_mapping"}
    session_id = _clean(session.get("session_id"))
    game = _clean(session.get("game"))
    events = session.get("events")
    if not session_id or not game or not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        return {"ok": False, "state": "ABSTAIN", "reason": "missing_session_identity_or_events", "session_id": session_id, "game": game}
    issues: list[str] = []
    for index, event in enumerate(list(events)[:MAX_EVENTS]):
        if not isinstance(event, Mapping) or not _clean(event.get("type")):
            issues.append(f"event_{index}_invalid")
    return {
        "ok": not issues,
        "state": "VERIFIED" if not issues else "ABSTAIN",
        "session_id": session_id,
        "game": game,
        "event_count": min(len(events), MAX_EVENTS),
        "issues": issues,
        "bounded": len(events) <= MAX_EVENTS,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "llm_authority": False,
    }


def analyze_session(session: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize events from one session with explicit evidence counts."""
    validation = validate_session(session)
    if not validation.get("ok"):
        return {"ok": False, "state": "ABSTAIN", "validation": validation, "writes_performed": False, "llm_authority": False}
    events = list(session.get("events") or [])[:MAX_EVENTS]
    deaths = [event for event in events if _clean(event.get("type")).casefold() == "death"]
    wins = [event for event in events if _clean(event.get("type")).casefold() == "win"]
    locations = Counter(_clean(_data(event).get("location")) or "unknown" for event in deaths)
    causes = Counter(_clean(_data(event).get("cause")) for event in deaths if _clean(_data(event).get("cause")))
    strategies = Counter(_clean(_data(event).get("strategy")) for event in wins if _clean(_data(event).get("strategy")))
    return {
        "ok": True,
        "state": "VERIFIED",
        "session_id": validation["session_id"],
        "game": validation["game"],
        "event_count": len(events),
        "total_deaths": len(deaths),
        "total_wins": len(wins),
        "death_locations": dict(sorted(locations.items(), key=lambda item: (-item[1], item[0]))),
        "common_mistakes": [name for name, _count in sorted(causes.items(), key=lambda item: (-item[1], item[0]))],
        "success_patterns": [name for name, _count in sorted(strategies.items(), key=lambda item: (-item[1], item[0]))],
        "evidence": {"source": "caller_supplied_session", "source_hash": _hash(dict(session))},
        "personal_only": True,
        "external_comparison": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def _valid_sessions(sessions: Sequence[Mapping[str, Any]], game_name: str) -> list[Mapping[str, Any]]:
    target = _clean(game_name).casefold()
    rows: list[Mapping[str, Any]] = []
    for session in list(sessions)[:MAX_SESSIONS]:
        validation = validate_session(session)
        if validation.get("ok") and str(validation.get("game", "")).casefold() == target:
            rows.append(session)
    return rows


def detect_patterns(sessions: Sequence[Mapping[str, Any]], game_name: str) -> dict[str, Any]:
    """Aggregate only supplied personal records; no semantic inference."""
    rows = _valid_sessions(sessions, game_name)
    analyses = [analyze_session(session) for session in rows]
    deaths = sum(int(row.get("total_deaths", 0)) for row in analyses)
    wins = sum(int(row.get("total_wins", 0)) for row in analyses)
    locations = Counter()
    mistakes = Counter()
    strategies = Counter()
    for row in analyses:
        locations.update(row.get("death_locations") or {})
        mistakes.update(row.get("common_mistakes") or [])
        strategies.update(row.get("success_patterns") or [])
    return {
        "ok": bool(rows),
        "state": "VERIFIED" if rows else "INSUFFICIENT",
        "game": _clean(game_name),
        "sessions": len(rows),
        "total_deaths": deaths,
        "total_wins": wins,
        "death_hotspots": dict(sorted(locations.items(), key=lambda item: (-item[1], item[0]))),
        "recurring_mistakes": [name for name, _count in sorted(mistakes.items(), key=lambda item: (-item[1], item[0]))],
        "success_patterns": [name for name, _count in sorted(strategies.items(), key=lambda item: (-item[1], item[0]))],
        "evidence_scope": "supplied_personal_sessions_only",
        "external_comparison": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def compare_to_self(sessions: Sequence[Mapping[str, Any]], game_name: str, *, max_sessions: int = 16) -> dict[str, Any]:
    """Compare the earliest and latest supplied sessions for the same game."""
    rows = _valid_sessions(sessions, game_name)[: max(2, min(int(max_sessions), MAX_SESSIONS))]
    if len(rows) < 2:
        return {"ok": False, "state": "INSUFFICIENT", "reason": "two_personal_sessions_required", "sessions": len(rows), "personal_only": True, "external_comparison": False, "writes_performed": False, "llm_authority": False}
    first = analyze_session(rows[0])
    recent = analyze_session(rows[-1])
    first_rate = first["total_deaths"] / max(1, first["event_count"])
    recent_rate = recent["total_deaths"] / max(1, recent["event_count"])
    if recent_rate < first_rate:
        direction = "improving"
    elif recent_rate > first_rate:
        direction = "more_deaths_in_recent_session"
    else:
        direction = "unchanged"
    return {
        "ok": True,
        "state": "VERIFIED",
        "game": _clean(game_name),
        "sessions_compared": len(rows),
        "first_session_id": first["session_id"],
        "recent_session_id": recent["session_id"],
        "first_death_rate_per_event": round(first_rate, 6),
        "recent_death_rate_per_event": round(recent_rate, 6),
        "direction": direction,
        "personal_only": True,
        "external_comparison": False,
        "evidence_scope": "earliest_and_latest_supplied_sessions",
        "writes_performed": False,
        "llm_authority": False,
    }


def plan_coaching(sessions: Sequence[Mapping[str, Any]], game_name: str) -> dict[str, Any]:
    """Produce evidence-linked coaching suggestions without rendering claims."""
    patterns = detect_patterns(sessions, game_name)
    if not patterns.get("ok"):
        return {"ok": False, "state": "INSUFFICIENT", "reason": "no_verified_personal_sessions", "patterns": patterns, "suggestions": [], "writes_performed": False, "llm_authority": False}
    suggestions: list[dict[str, Any]] = []
    hotspots = patterns.get("death_hotspots") or {}
    mistakes = patterns.get("recurring_mistakes") or []
    successes = patterns.get("success_patterns") or []
    if hotspots:
        location, count = next(iter(hotspots.items()))
        suggestions.append({"kind": "focus_area", "text": f"Review the supplied events for {location}.", "evidence": {"death_count": count, "location": location}})
    if mistakes:
        suggestions.append({"kind": "mistake_review", "text": f"Review the recurring supplied cause: {mistakes[0]}.", "evidence": {"cause": mistakes[0]}})
    if successes:
        suggestions.append({"kind": "strength", "text": f"Retain the supplied success pattern: {successes[0]}.", "evidence": {"strategy": successes[0]}})
    comparison = compare_to_self(sessions, game_name)
    if comparison.get("ok"):
        suggestions.append({"kind": "trend", "text": f"Your supplied session trend is {comparison['direction']}.", "evidence": comparison})
    return {
        "ok": True,
        "state": "VERIFIED",
        "game": _clean(game_name),
        "suggestions": suggestions,
        "patterns": patterns,
        "comparison": comparison,
        "claim_scope": "supplied_personal_sessions_only",
        "no_external_ranking": True,
        "writes_performed": False,
        "llm_authority": False,
    }


def plan_session_event(session_id: str, event_type: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare an event append intent without applying it."""
    clean_id = _clean(session_id)
    clean_type = _clean(event_type).casefold()
    payload = dict(data) if isinstance(data, Mapping) else {}
    ok = bool(clean_id and clean_type and isinstance(data, Mapping))
    return {
        "ok": ok,
        "state": "PROPOSED" if ok else "ABSTAIN",
        "session_id": clean_id,
        "event_type": clean_type,
        "data": payload,
        "event_hash": _hash({"session_id": clean_id, "event_type": clean_type, "data": payload}) if ok else None,
        "append_required": ok,
        "applied": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def module_status() -> dict[str, Any]:
    return {
        "ok": True,
        "state": "READY",
        "module": MODULE_ID,
        "version": VERSION,
        "manual_section": MANUAL_SECTION,
        "read_only": True,
        "personal_only": True,
        "external_comparison": False,
        "llm_authority": False,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
    }
