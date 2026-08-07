"""Focused regression tests for the effect-closed game analytics slice."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.game_core import analyze_session, compare_to_self, detect_patterns, module_status, plan_coaching, plan_session_event, validate_session


def _sessions() -> list[dict[str, object]]:
    return [
        {"session_id": "s1", "game": "Example", "events": [{"type": "death", "data": {"location": "gate", "cause": "early roll"}}, {"type": "win", "data": {"strategy": "wait"}}]},
        {"session_id": "s2", "game": "Example", "events": [{"type": "win", "data": {"strategy": "wait"}}]},
    ]


def test_validation_and_analysis_are_evidence_bound() -> None:
    session = _sessions()[0]
    assert validate_session(session)["ok"] is True
    result = analyze_session(session)
    assert result["ok"] is True
    assert result["total_deaths"] == 1
    assert result["death_locations"] == {"gate": 1}
    assert result["evidence"]["source"] == "caller_supplied_session"
    assert result["writes_performed"] is False


def test_personal_patterns_and_comparison_never_use_external_ranking() -> None:
    sessions = _sessions()
    patterns = detect_patterns(sessions, "Example")
    comparison = compare_to_self(sessions, "Example")
    assert patterns["ok"] is True
    assert patterns["external_comparison"] is False
    assert comparison["ok"] is True
    assert comparison["personal_only"] is True
    assert comparison["direction"] == "improving"


def test_coaching_and_event_intent_are_non_mutating() -> None:
    sessions = _sessions()
    coaching = plan_coaching(sessions, "Example")
    event = plan_session_event("s2", "milestone", {"name": "first clear"})
    assert coaching["ok"] is True
    assert coaching["no_external_ranking"] is True
    assert event["ok"] is True
    assert event["applied"] is False
    assert event["writes_performed"] is False


def test_malformed_and_missing_data_abstain() -> None:
    assert validate_session({"session_id": "bad", "game": "Example"})["ok"] is False
    assert plan_coaching([], "Example")["state"] == "INSUFFICIENT"


def test_no_forbidden_effects_or_model_imports() -> None:
    tree = ast.parse((ROOT / "lib" / "game_core.py").read_text(encoding="utf-8"))
    forbidden = {"subprocess", "socket", "requests", "torch", "numpy", "pathlib"}
    assert all(not isinstance(node, ast.ImportFrom) or node.module not in forbidden for node in ast.walk(tree))
    assert all(not isinstance(node, ast.Import) or all(alias.name not in forbidden for alias in node.names) for node in ast.walk(tree))


def test_module_status() -> None:
    result = module_status()
    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["personal_only"] is True
    assert result["llm_authority"] is False
