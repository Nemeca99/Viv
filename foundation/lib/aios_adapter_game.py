"""Read-only adapter for game_core personal analytics and coaching."""
from __future__ import annotations

from typing import Any

from lib.cpu_choice_simulator import evaluate_candidates
from lib.game_core import analyze_session, module_status, plan_coaching, plan_session_event


def status() -> dict[str, Any]:
    return module_status()


def cpu_plan(
    sessions: list[dict[str, Any]],
    *,
    game_name: str,
    event_intent: dict[str, Any] | None = None,
    choice_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analyses = [analyze_session(session) for session in list(sessions)[:128]]
    result: dict[str, Any] = {
        "ok": bool(analyses),
        "state": "VERIFIED" if analyses else "INSUFFICIENT",
        "game": str(game_name),
        "session_analyses": analyses,
        "coaching": plan_coaching(sessions, game_name),
        "writes_performed": False,
        "llm_authority": False,
        "personal_only": True,
        "external_comparison": False,
    }
    if event_intent is not None:
        result["event_intent"] = plan_session_event(
            str(event_intent.get("session_id") or ""),
            str(event_intent.get("event_type") or ""),
            event_intent.get("data") if isinstance(event_intent.get("data"), dict) else {},
        )
    if choice_state is not None:
        result["choice_candidates"] = evaluate_candidates(choice_state)
    return result


def run_smoke() -> dict[str, Any]:
    sessions = [
        {
            "session_id": "session_1",
            "game": "Example",
            "events": [
                {"type": "death", "data": {"location": "gate", "cause": "early roll"}},
                {"type": "win", "data": {"location": "gate", "strategy": "wait then dodge"}},
            ],
        },
        {
            "session_id": "session_2",
            "game": "Example",
            "events": [{"type": "win", "data": {"location": "gate", "strategy": "wait then dodge"}}],
        },
    ]
    result = cpu_plan(
        sessions,
        game_name="Example",
        event_intent={"session_id": "session_2", "event_type": "milestone", "data": {"name": "first clear"}},
        choice_state={"s_n": 0.6, "queued_work": 1},
    )
    return {
        "ok": bool(result.get("ok") and result["coaching"].get("ok") and not result.get("event_intent", {}).get("applied")),
        "state": "PASS" if result.get("ok") else "INCONCLUSIVE",
        "plan": result,
        "authority": "cpu_adapter_observation",
        "adapter_output_is_authority": False,
    }
