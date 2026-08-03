"""Standing goals — Architect sets high-level objective; Viv owns the how.

Level 3 Conditional Autonomy: goals persist under Law 7 sandbox/work/.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.aios_sandbox import WORK, ensure_sandbox_home

GOALS_PATH = WORK / "goals.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_goals() -> dict[str, Any]:
    ensure_sandbox_home()
    WORK.mkdir(parents=True, exist_ok=True)
    if not GOALS_PATH.is_file():
        payload = {"version": 1, "goals": [], "updated_at": _utc()}
        GOALS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    try:
        return json.loads(GOALS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "goals": [], "updated_at": _utc()}


def save_goals(data: dict[str, Any]) -> None:
    ensure_sandbox_home()
    data["updated_at"] = _utc()
    tmp = GOALS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(GOALS_PATH)


def list_goals(*, status: str | None = None) -> list[dict[str, Any]]:
    goals = list((ensure_goals().get("goals") or []))
    if status:
        goals = [g for g in goals if str(g.get("status")) == status]
    return goals


def get_goal(goal_id: str) -> dict[str, Any] | None:
    for g in list_goals():
        if g.get("goal_id") == goal_id:
            return g
    return None


def upsert_goal(goal: dict[str, Any]) -> dict[str, Any]:
    data = ensure_goals()
    goals = list(data.get("goals") or [])
    gid = str(goal.get("goal_id") or "")
    found = False
    for i, g in enumerate(goals):
        if g.get("goal_id") == gid:
            goals[i] = goal
            found = True
            break
    if not found:
        goals.append(goal)
    data["goals"] = goals
    save_goals(data)
    return goal


def add_goal(
    objective: str,
    *,
    success: str = "",
    priority: int = 50,
    source: str = "architect",
) -> dict[str, Any]:
    """Seed a high-level goal. Agent decomposes steps — Architect does not micromanage."""
    obj = (objective or "").strip()
    if not obj:
        raise ValueError("empty_objective")
    goal = {
        "goal_id": f"g-{uuid.uuid4().hex[:10]}",
        "objective": obj,
        "success_criteria": (success or f"Objective complete: {obj[:80]}").strip(),
        "priority": int(priority),
        "status": "active",  # active | blocked | done | handed_off
        "source": source,
        "plan": [],  # filled by reason phase
        "step_index": 0,
        "attempts": 0,
        "max_attempts": 8,
        "last_error": None,
        "last_result": None,
        "created_at": _utc(),
        "updated_at": _utc(),
    }
    return upsert_goal(goal)


def active_goal() -> dict[str, Any] | None:
    """Highest priority active goal (agency: she picks what to work on)."""
    actives = [g for g in list_goals(status="active")]
    if not actives:
        return None
    actives.sort(key=lambda g: (int(g.get("priority") or 100), str(g.get("created_at") or "")))
    return actives[0]


def propose_default_goals_if_empty() -> list[dict[str, Any]]:
    """If board empty, propose ABSORB real V1/V2 cores — not sandbox toys."""
    if list_goals(status="active") or list_goals(status="blocked"):
        return []
    ensure_sandbox_home()
    added: list[dict[str, Any]] = []
    g = add_goal(
        "Absorb next LEGACY AIOS core from V1/V2 into Viv: systems registry, steel judge, knowledge",
        success="AIOS_SYSTEMS_REGISTRY.md written; steel_judge + knowledge absorb artifacts exist",
        priority=5,
        source="cpu_propose",
    )
    added.append(g)
    return added


def retire_maintenance_goals() -> list[str]:
    """Hand off old maintenance / sandbox-toy goals so absorb owns the board."""
    retired: list[str] = []
    keywords = (
        "maintain plant",
        "sandbox healthy",
        "consolidate memory",
        "consolidate dream",
        "invent novel tool",
        "capability module in sandbox",
    )
    for g in list_goals(status="active"):
        obj = (g.get("objective") or "").lower()
        if any(k in obj for k in keywords) and "absorb" not in obj:
            mark_goal(
                g["goal_id"],
                status="handed_off",
                error="retired_for_real_system_absorb",
            )
            retired.append(g["goal_id"])
    return retired

def mark_goal(goal_id: str, *, status: str, error: str | None = None, result: str | None = None) -> dict[str, Any] | None:
    g = get_goal(goal_id)
    if not g:
        return None
    g["status"] = status
    g["updated_at"] = _utc()
    if error is not None:
        g["last_error"] = error
    if result is not None:
        g["last_result"] = result
    return upsert_goal(g)
