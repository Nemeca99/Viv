"""Level 3 agentic loop: perceive → reason → act → learn.

Architect sets high-level goals. Viv chooses steps and when to act (autonomy),
revises on failure (adaptability), pursues objective (goal orientation).
GPU does not own this loop.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.aios_goals import (
    active_goal,
    get_goal,
    mark_goal,
    propose_default_goals_if_empty,
    retire_maintenance_goals,
    upsert_goal,
)
from lib.aios_sandbox import JOURNAL, WORK, ensure_sandbox_home
from lib.master_rid import load_master_rid
from lib.security_membrane import tool_gate

ATTEMPTS_LOG = JOURNAL / "autonomy_attempts.jsonl"
AGENT_STATE = WORK / "agent_state.json"
DORMANCY = 0.37


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_attempt(row: dict[str, Any]) -> None:
    ensure_sandbox_home()
    JOURNAL.mkdir(parents=True, exist_ok=True)
    with ATTEMPTS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _gated_write(path: Path, content: str, s_n: float) -> tuple[bool, str]:
    gate = str(path).replace("\\", "/")
    verdict = tool_gate("write_file", {"path": gate, "content": content}, s_n)
    if not verdict.get("allowed"):
        return False, str(verdict.get("reason", "denied"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True, "ok"


# --- Perceive ---

def perceive() -> dict[str, Any]:
    ensure_sandbox_home()
    retired = retire_maintenance_goals()
    proposed = propose_default_goals_if_empty()
    try:
        m = load_master_rid()
        plant = {
            "master_s_n": float(m.master_s_n),
            "status": m.status,
            "rsr": m.master_rsr,
            "ltp": m.master_ltp,
            "rle": m.master_rle,
        }
        sn = float(m.master_s_n)
    except Exception as exc:  # noqa: BLE001
        plant = {"error": str(exc)}
        sn = 0.5

    goal = active_goal()
    carma_hits: list[dict[str, Any]] = []
    if goal:
        try:
            from lib.carma_memory import retrieve

            carma_hits = retrieve(str(goal.get("objective") or "goal")[:80], top=3)
        except Exception:
            carma_hits = []

    return {
        "at": _utc(),
        "plant": plant,
        "s_n": sn,
        "goal": goal,
        "proposed_goals": [g.get("goal_id") for g in proposed],
        "retired_maintenance": retired,
        "carma_hits": [{"text": (h.get("text") or "")[:120]} for h in carma_hits],
        "dormant": sn < DORMANCY,
    }


# --- Reason ---

def _default_plan(objective: str) -> list[dict[str, Any]]:
    """Decompose high-level objective into actionable steps (CPU, not GPU)."""
    low = objective.lower()
    # Primary: absorb real V1/V2 systems into Viv
    if any(k in low for k in ("absorb", "system", "core", "legacy", "v1", "v2", "steel", "knowledge", "rag", "tool_core")):
        steps: list[dict[str, Any]] = [
            {"id": "survey_systems", "kind": "survey_systems", "title": "Scan V1+V2 systems registry"},
            {"id": "absorb_next", "kind": "absorb_next", "title": "Absorb next LEGACY core into Viv"},
            {"id": "steel_judge_check", "kind": "steel_judge_check", "title": "Run CPU Steel Judge gate"},
            {"id": "knowledge_absorb", "kind": "knowledge_absorb", "title": "Absorb architecture knowledge"},
            {"id": "remember", "kind": "remember", "title": "Remember absorb progress in CARMA"},
            {"id": "verify_absorb", "kind": "verify_absorb", "title": "Verify registry + absorb artifacts"},
        ]
    elif any(k in low for k in ("build", "invent", "aios", "author", "module", "capability")):
        steps = [
            {"id": "survey_systems", "kind": "survey_systems", "title": "Scan real AIOS systems gaps"},
            {"id": "absorb_next", "kind": "absorb_next", "title": "Absorb next LEGACY core"},
            {"id": "remember", "kind": "remember", "title": "Remember progress"},
            {"id": "verify_absorb", "kind": "verify_absorb", "title": "Verify absorb evidence"},
        ]
    else:
        steps = [
            {"id": "survey_systems", "kind": "survey_systems", "title": "Scan AIOS systems"},
            {"id": "absorb_next", "kind": "absorb_next", "title": "Absorb next core"},
            {"id": "remember", "kind": "remember", "title": "Remember progress"},
            {"id": "verify_absorb", "kind": "verify_absorb", "title": "Verify absorb"},
        ]
    for s in steps:
        s["status"] = "pending"
        s["result"] = None
        s["tries"] = 0
    return steps


def reason(perception: dict[str, Any]) -> dict[str, Any]:
    if perception.get("dormant"):
        return {
            "decision": "handoff",
            "reason": "s_n_dormancy",
            "s_n": perception.get("s_n"),
            "step": None,
            "goal": perception.get("goal"),
        }

    goal = perception.get("goal")
    if not goal:
        return {"decision": "idle", "reason": "no_active_goal", "step": None, "goal": None}

    if int(goal.get("attempts") or 0) >= int(goal.get("max_attempts") or 8):
        mark_goal(goal["goal_id"], status="handed_off", error="retry_budget_exhausted")
        return {
            "decision": "handoff",
            "reason": "retry_budget_exhausted",
            "step": None,
            "goal": get_goal(goal["goal_id"]),
        }

    plan = list(goal.get("plan") or [])
    if not plan:
        plan = _default_plan(str(goal.get("objective") or ""))
        goal["plan"] = plan
        goal["step_index"] = 0
        goal["updated_at"] = _utc()
        upsert_goal(goal)

    # Find next pending step
    idx = int(goal.get("step_index") or 0)
    step = None
    for i in range(idx, len(plan)):
        if plan[i].get("status") in (None, "pending", "failed"):
            step = plan[i]
            goal["step_index"] = i
            break
    if step is None:
        mark_goal(goal["goal_id"], status="done", result="all_steps_complete")
        return {
            "decision": "done",
            "reason": "plan_complete",
            "step": None,
            "goal": get_goal(goal["goal_id"]),
        }

    return {
        "decision": "act",
        "reason": "next_step",
        "step": step,
        "goal": goal,
        "s_n": perception.get("s_n"),
    }


# --- Act ---

def _act_measure_plant(s_n: float) -> dict[str, Any]:
    try:
        from lib.rid_feed import pulse_once
        from lib.master_rid import compute_master_rid, publish_master_rid

        sample = pulse_once()
        master = compute_master_rid(sample)
        publish_master_rid(master)
        return {
            "ok": True,
            "stdout": f"S_n={master.master_s_n:.4f} status={master.status}",
            "s_n": master.master_s_n,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _act_plant_brief(s_n: float) -> dict[str, Any]:
    try:
        m = load_master_rid()
        path = WORK / "plant_brief.txt"
        line = (
            f"[{_utc()}] Master S_n={m.master_s_n:.4f} status={m.status} "
            f"RSR={m.master_rsr:.4f} LTP={m.master_ltp:.4f} RLE={m.master_rle:.4f}\n"
        )
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        ok, reason = _gated_write(path, existing + line, s_n)
        return {"ok": ok, "stdout": reason if ok else reason, "path": str(path).replace("\\", "/")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _act_dream(s_n: float) -> dict[str, Any]:
    try:
        from lib.aios_dream import perform_dream_cycle

        out = perform_dream_cycle(force=True)
        return {
            "ok": bool(out.get("ok")),
            "stdout": f"dream cycle={out.get('cycle')} path={out.get('dream_path')}",
            "skipped": out.get("skipped"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _act_ensure_tools(s_n: float) -> dict[str, Any]:
    try:
        from lib.aios_coder import run_sandbox_tool, write_and_run

        results = []
        for tool in ("plant_digest", "memory_census", "sandbox_health"):
            out = write_and_run(tool=tool)
            results.append({"tool": tool, "ok": out.get("ok"), "stdout": ((out.get("run") or {}).get("stdout") or "")[:120]})
        ok = all(r.get("ok") for r in results)
        return {"ok": ok, "stdout": json.dumps(results)[:400]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _act_sandbox_health(s_n: float) -> dict[str, Any]:
    try:
        from lib.aios_coder import run_sandbox_tool

        rn = run_sandbox_tool(tool="sandbox_health", s_n=s_n)
        return {"ok": bool(rn.get("ok")), "stdout": (rn.get("stdout") or "")[:300]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _act_remember(goal: dict[str, Any], s_n: float) -> dict[str, Any]:
    try:
        from lib.carma_memory import remember

        text = (
            f"[goal] {goal.get('objective')} progress={goal.get('step_index')}/"
            f"{len(goal.get('plan') or [])} status={goal.get('status')}"
        )
        out = remember(text, provenance="live", tags=["goal", "agent", "learn"], s_n=s_n)
        return {"ok": bool(out.get("ok")), "stdout": str(out.get("id") or out.get("reason"))}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _act_verify(goal: dict[str, Any]) -> dict[str, Any]:
    plan = goal.get("plan") or []
    pending = [
        s
        for s in plan
        if s.get("id") not in {"verify", "verify_build", "verify_absorb"} and s.get("status") != "done"
    ]
    if pending:
        return {"ok": False, "error": f"steps_incomplete:{[s.get('id') for s in pending]}"}
    return {"ok": True, "stdout": "criteria_met"}


def _act_survey_gaps(s_n: float) -> dict[str, Any]:
    from lib.aios_builder import survey_gaps

    out = survey_gaps()
    return {
        "ok": True,
        "stdout": f"next={out.get('next')} missing={len(out.get('missing') or [])} have={len(out.get('have') or [])}",
        "survey": out,
    }


def _act_survey_systems(s_n: float) -> dict[str, Any]:
    from lib.aios_absorb import survey_and_write_registry

    return survey_and_write_registry()


def _act_absorb_next(goal: dict[str, Any], s_n: float) -> dict[str, Any]:
    from lib.aios_absorb import absorb_next

    out = absorb_next(s_n=s_n)
    if out.get("ok"):
        goal["absorb_module"] = (out.get("next_was") or {}).get("id") or out.get("module")
        goal["absorb_path"] = out.get("path")
        upsert_goal(goal)
    return out


def _act_steel_judge_check(s_n: float) -> dict[str, Any]:
    from lib.aios_absorb import absorb_steel_judge

    return absorb_steel_judge(s_n=s_n)


def _act_knowledge_absorb(s_n: float) -> dict[str, Any]:
    from lib.aios_absorb import absorb_knowledge

    return absorb_knowledge(s_n=s_n)


def _act_verify_absorb() -> dict[str, Any]:
    from lib.aios_systems import REGISTRY_JSON, REGISTRY_MD, write_registry
    from lib.paths import AUTO_ARTIFACTS

    write_registry()
    judge = AUTO_ARTIFACTS / "steel_judge" / "equilibrium.json"
    know = AUTO_ARTIFACTS / "knowledge" / "absorb_index.json"
    missing = []
    if not REGISTRY_JSON.is_file():
        missing.append("registry_json")
    if not REGISTRY_MD.is_file():
        missing.append("registry_md")
    if not judge.is_file():
        missing.append("steel_judge")
    if not know.is_file():
        missing.append("knowledge_index")
    if missing:
        return {"ok": False, "error": f"missing:{missing}"}
    return {
        "ok": True,
        "stdout": (
            f"verified registry={REGISTRY_MD} "
            f"steel_judge={judge} knowledge={know}"
        ),
    }


def _act_invent_module(goal: dict[str, Any], s_n: float) -> dict[str, Any]:
    from lib.aios_builder import invent_next_module

    out = invent_next_module(s_n=s_n)
    if out.get("ok"):
        goal["build_module"] = out.get("module")
        goal["build_path"] = out.get("path")
        goal["build_why"] = out.get("why")
        upsert_goal(goal)
    return out


def _act_run_module(goal: dict[str, Any], s_n: float) -> dict[str, Any]:
    from lib.aios_builder import run_module

    module = str(goal.get("build_module") or "")
    if not module:
        return {"ok": False, "error": "no_build_module_on_goal"}
    out = run_module(module=module, s_n=s_n)
    if out.get("ok"):
        goal["build_run_stdout"] = (out.get("stdout") or "")[:400]
        upsert_goal(goal)
    return out


def _act_write_build_manifest(goal: dict[str, Any], s_n: float) -> dict[str, Any]:
    from lib.aios_builder import write_manifest

    module = str(goal.get("build_module") or "")
    path = str(goal.get("build_path") or "")
    why = str(goal.get("build_why") or "AIOS capability module")
    run_stdout = str(goal.get("build_run_stdout") or "")
    if not module or not path:
        return {"ok": False, "error": "missing_module_or_path"}
    return write_manifest(module=module, path=path, why=why, run_stdout=run_stdout, s_n=s_n)


def _act_verify_build() -> dict[str, Any]:
    from lib.aios_builder import verify_last_build

    return verify_last_build()


def act(decision: dict[str, Any], perception: dict[str, Any]) -> dict[str, Any]:
    if decision.get("decision") != "act":
        return {"ok": True, "skipped": decision.get("decision"), "decision": decision}

    goal = decision.get("goal") or {}
    step = decision.get("step") or {}
    sn = float(perception.get("s_n") or 0.5)
    kind = str(step.get("kind") or "")

    handlers = {
        "measure_plant": lambda: _act_measure_plant(sn),
        "plant_brief": lambda: _act_plant_brief(sn),
        "dream": lambda: _act_dream(sn),
        "ensure_tools": lambda: _act_ensure_tools(sn),
        "sandbox_health": lambda: _act_sandbox_health(sn),
        "remember": lambda: _act_remember(goal, sn),
        "verify": lambda: _act_verify(goal),
        "survey_gaps": lambda: _act_survey_gaps(sn),
        "survey_systems": lambda: _act_survey_systems(sn),
        "absorb_next": lambda: _act_absorb_next(goal, sn),
        "steel_judge_check": lambda: _act_steel_judge_check(sn),
        "knowledge_absorb": lambda: _act_knowledge_absorb(sn),
        "verify_absorb": lambda: _act_verify_absorb(),
        "invent_module": lambda: _act_invent_module(goal, sn),
        "run_module": lambda: _act_run_module(goal, sn),
        "write_build_manifest": lambda: _act_write_build_manifest(goal, sn),
        "verify_build": lambda: _act_verify_build(),
    }
    fn = handlers.get(kind)
    if not fn:
        return {"ok": False, "error": f"unknown_kind:{kind}", "step": step, "goal_id": goal.get("goal_id")}

    result = fn()
    result["step"] = step
    result["goal_id"] = goal.get("goal_id")
    result["kind"] = kind
    return result


# --- Learn ---

def learn(perception: dict[str, Any], decision: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    goal = decision.get("goal")
    if not goal:
        return {"ok": True, "note": "no_goal"}

    gid = goal.get("goal_id")
    fresh = get_goal(str(gid)) or goal
    plan = list(fresh.get("plan") or [])
    idx = int(fresh.get("step_index") or 0)
    sn = float(perception.get("s_n") or 0.5)

    if decision.get("decision") == "handoff":
        _append_attempt(
            {
                "event": "handoff",
                "at": _utc(),
                "goal_id": gid,
                "reason": decision.get("reason"),
                "s_n": sn,
            }
        )
        return {"ok": True, "handed_off": True, "reason": decision.get("reason")}

    if decision.get("decision") == "done":
        _append_attempt({"event": "goal_done", "at": _utc(), "goal_id": gid, "s_n": sn})
        _maybe_speak(f"Goal complete: {fresh.get('objective')}", sn)
        return {"ok": True, "done": True}

    if decision.get("decision") != "act":
        return {"ok": True, "note": decision.get("decision")}

    step = decision.get("step") or {}
    ok = bool(action.get("ok"))
    # Update step in plan
    for i, s in enumerate(plan):
        if s.get("id") == step.get("id"):
            s["tries"] = int(s.get("tries") or 0) + 1
            if ok:
                s["status"] = "done"
                s["result"] = (action.get("stdout") or "")[:240]
                fresh["step_index"] = i + 1
            else:
                s["status"] = "failed"
                s["result"] = str(action.get("error") or action.get("stdout") or "fail")[:240]
                # Adaptability: on first fail, replan by inserting alternate ensure_tools before retry
                if int(s.get("tries") or 0) == 1 and s.get("kind") not in {"ensure_tools", "measure_plant"}:
                    alt = {
                        "id": f"heal_{s.get('id')}",
                        "kind": "ensure_tools",
                        "title": f"Heal before retry {s.get('id')}",
                        "status": "pending",
                        "result": None,
                        "tries": 0,
                    }
                    plan.insert(i, alt)
                    fresh["step_index"] = i
                    s["status"] = "pending"  # will retry after heal
                elif int(s.get("tries") or 0) >= 3:
                    # escalate
                    fresh["attempts"] = int(fresh.get("attempts") or 0) + 1
                    mark_goal(str(gid), status="handed_off", error=f"step_failed:{s.get('id')}")
                    _append_attempt(
                        {
                            "event": "handoff",
                            "at": _utc(),
                            "goal_id": gid,
                            "reason": "step_failed_exhausted",
                            "step": s.get("id"),
                            "error": s.get("result"),
                        }
                    )
                    _maybe_speak(f"Handing off: step {s.get('id')} failed repeatedly.", sn)
                    return {"ok": False, "handed_off": True, "step": s.get("id")}
            plan[i] = s
            break

    fresh["plan"] = plan
    fresh["attempts"] = int(fresh.get("attempts") or 0) + (0 if ok else 1)
    fresh["last_result"] = (action.get("stdout") or action.get("error") or "")[:240]
    fresh["last_error"] = None if ok else fresh["last_result"]
    fresh["updated_at"] = _utc()
    upsert_goal(fresh)

    _append_attempt(
        {
            "event": "step",
            "at": _utc(),
            "goal_id": gid,
            "step": step.get("id"),
            "kind": step.get("kind"),
            "ok": ok,
            "stdout": (action.get("stdout") or "")[:200],
            "error": action.get("error"),
            "s_n": sn,
        }
    )

    # Learn note in CARMA on failures (adaptability evidence)
    if not ok:
        try:
            from lib.carma_memory import remember

            remember(
                f"[learn] goal={gid} step={step.get('id')} fail={action.get('error')}",
                provenance="live",
                tags=["learn", "agent", "fail"],
                s_n=sn,
            )
        except Exception:
            pass

    if ok and step.get("kind") in {
        "verify",
        "verify_build",
        "verify_absorb",
        "invent_module",
        "absorb_next",
        "remember",
    }:
        _maybe_speak(f"Progress on goal: {step.get('title') or step.get('id')}", sn)

    return {"ok": ok, "goal_id": gid, "step": step.get("id"), "adapted": not ok}


def _maybe_speak(text: str, s_n: float) -> None:
    if s_n < DORMANCY:
        return
    try:
        from lib.aios_personality import render_cpu_line

        line = render_cpu_line(deltas=[text[:80]], stdout="", status="ACTIVE", s_n=s_n)
        # Store last speak on agent state (organism prints it)
        ensure_sandbox_home()
        st = {"at": _utc(), "text": line or text, "s_n": s_n}
        AGENT_STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")
    except Exception:
        ensure_sandbox_home()
        AGENT_STATE.write_text(json.dumps({"at": _utc(), "text": text, "s_n": s_n}, indent=2), encoding="utf-8")


def agent_cycle() -> dict[str, Any]:
    """One full autonomous cycle."""
    perception = perceive()
    decision = reason(perception)
    action = act(decision, perception)
    learned = learn(perception, decision, action)

    spoken = ""
    if AGENT_STATE.is_file():
        try:
            spoken = str(json.loads(AGENT_STATE.read_text(encoding="utf-8")).get("text") or "")
        except (OSError, json.JSONDecodeError):
            spoken = ""

    # Speak only on progress / heal / handoff / done — never every beat
    speak_text = ""
    if decision.get("decision") in {"done", "handoff"}:
        speak_text = spoken
    elif learned.get("adapted") and not action.get("ok"):
        speak_text = spoken
    elif action.get("ok") and (decision.get("step") or {}).get("kind") in {
        "verify",
        "verify_build",
        "invent_module",
        "plant_brief",
        "dream",
    }:
        speak_text = spoken

    # Consume so the same line is not reprinted next beat
    if speak_text and AGENT_STATE.is_file():
        try:
            AGENT_STATE.write_text(json.dumps({"at": _utc(), "text": "", "consumed": True}, indent=2), encoding="utf-8")
        except OSError:
            pass

    return {
        "ok": True,
        "at": _utc(),
        "perceive": {
            "s_n": perception.get("s_n"),
            "dormant": perception.get("dormant"),
            "goal_id": (perception.get("goal") or {}).get("goal_id"),
            "objective": ((perception.get("goal") or {}).get("objective") or "")[:120],
            "proposed": perception.get("proposed_goals"),
        },
        "reason": {
            "decision": decision.get("decision"),
            "reason": decision.get("reason"),
            "step": (decision.get("step") or {}).get("id"),
            "kind": (decision.get("step") or {}).get("kind"),
        },
        "act": {
            "ok": action.get("ok"),
            "kind": action.get("kind"),
            "stdout": (action.get("stdout") or "")[:240],
            "error": action.get("error"),
            "skipped": action.get("skipped"),
        },
        "learn": learned,
        "spoken": speak_text[:280],
        "attempts_log": str(ATTEMPTS_LOG).replace("\\", "/"),
    }
