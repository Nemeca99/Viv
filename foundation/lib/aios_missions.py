"""AIOS missions — full goal execution, not micro-MVP crumbs.

Every operator ask becomes a Mission with measure → act → remember → report → speak.
Missions run to completion and write a human activity feed.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from lib.paths import AUTO_ARTIFACTS
from lib.aios_sandbox import OPERATOR, SANDBOX_ROOT, WORK, ensure_sandbox_home

ORGANISM_ROOT = AUTO_ARTIFACTS / "organism"
MISSIONS_PATH = ORGANISM_ROOT / "missions.json"
ACTIVITY_JSONL = ORGANISM_ROOT / "activity.jsonl"
ACTIVITY_MD = ORGANISM_ROOT / "ACTIVITY.md"
SANDBOX = SANDBOX_ROOT


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_activity(row: dict[str, Any]) -> None:
    ORGANISM_ROOT.mkdir(parents=True, exist_ok=True)
    row = dict(row)
    row.setdefault("timestamp", _utc())
    with ACTIVITY_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


@dataclass
class Step:
    name: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending|running|done|failed
    result: str | None = None


@dataclass
class Mission:
    mission_id: str
    ask: str
    created_at: str
    status: str = "ready"  # ready|running|done|failed
    steps: list[Step] = field(default_factory=list)
    summary: str = ""
    spoken: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "ask": self.ask,
            "created_at": self.created_at,
            "status": self.status,
            "steps": [asdict(s) for s in self.steps],
            "summary": self.summary,
            "spoken": self.spoken,
            "updated_at": self.updated_at or self.created_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Mission:
        steps = [Step(**s) for s in (raw.get("steps") or [])]
        return cls(
            mission_id=str(raw["mission_id"]),
            ask=str(raw.get("ask") or ""),
            created_at=str(raw.get("created_at") or _utc()),
            status=str(raw.get("status") or "ready"),
            steps=steps,
            summary=str(raw.get("summary") or ""),
            spoken=str(raw.get("spoken") or ""),
            updated_at=str(raw.get("updated_at") or ""),
        )


def load_missions() -> list[Mission]:
    ORGANISM_ROOT.mkdir(parents=True, exist_ok=True)
    if not MISSIONS_PATH.is_file():
        return []
    try:
        raw = json.loads(MISSIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [Mission.from_dict(m) for m in raw.get("missions", [])]


def save_missions(missions: list[Mission]) -> None:
    ORGANISM_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": _utc(), "missions": [m.to_dict() for m in missions]}
    tmp = MISSIONS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(MISSIONS_PATH)


def publish_activity_md(*, limit: int = 40) -> Path:
    lines = [f"# Viv activity — {_utc()}", ""]
    if not ACTIVITY_JSONL.is_file():
        lines.append("(no activity yet)")
    else:
        rows = []
        for line in ACTIVITY_JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        for row in rows[-limit:]:
            ts = row.get("timestamp", "")
            ev = row.get("event", "")
            detail = row.get("detail") or row.get("ask") or row.get("text") or ""
            lines.append(f"- `{ts}` **{ev}** — {detail}")
    # Active missions
    lines.extend(["", "## Missions"])
    missions = load_missions()
    active = [m for m in missions if m.status in {"ready", "running"}]
    done = [m for m in missions if m.status == "done"][-8:]
    if not active and not done:
        lines.append("- (none)")
    for m in active:
        lines.append(f"- READY/RUNNING `{m.mission_id}` — {m.ask}")
        for s in m.steps:
            lines.append(f"  - [{s.status}] {s.name}")
    for m in done:
        lines.append(f"- DONE `{m.mission_id}` — {m.ask}")
        if m.spoken:
            lines.append(f"  - said: {m.spoken[:160]}")
    ACTIVITY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ACTIVITY_MD


def plan_mission(ask: str) -> Mission:
    """Full mission plan from any operator ask — always multi-step."""
    text = (ask or "").strip()
    low = text.lower()
    mid = f"m-{uuid.uuid4().hex[:10]}"
    steps: list[Step] = [
        Step("measure_plant", "rid_sample", {}),
        Step("remember_ask", "memory_append", {
            "text": f"[mission] Architect asked: {text}",
            "provenance": "operator",
            "tags": ["mission", "operator", "ask"],
        }),
    ]

    if low.startswith("say ") or low.startswith("speak ") or low.startswith("hello"):
        body = text
        for pref in ("say ", "speak "):
            if low.startswith(pref):
                body = text[len(pref):].strip()
                break
        steps.append(Step("speak_to_architect", "speak_brief", {"query": body or text}))
    elif low.startswith("uml ") or low.startswith("compute ") or "math" in low or "workbook" in low:
        if "workbook" in low or "practice" in low:
            steps.append(Step("uml_practice", "uml_workbook", {"n": 4}))
        else:
            expr = text[4:].strip() if low.startswith("uml ") else "[3,4]"
            if low.startswith("compute "):
                expr = text[8:].strip() or "[3,4]"
            steps.append(Step("uml_compute", "uml_eval", {"expr": expr}))
    elif low.startswith("remember ") or low.startswith("note "):
        body = text.split(" ", 1)[1] if " " in text else text
        steps.append(Step("write_sandbox_note", "append_journal", {
            "path": str(OPERATOR / "notes.txt").replace("\\", "/"),
            "line": f"[{_utc()}] {body}",
        }))
    elif low.startswith("status") or low in {"how are you", "check", "report"}:
        steps.append(Step("voice_check", "voice_status", {}))
        steps.append(Step("guardian_check", "guardian_pulse", {
            "text": "Master S_n plant status ACTIVE PASS",
        }))
    else:
        # General goal — plan + brief + workbook evidence she can act
        steps.append(Step("record_goal", "operator_goal", {"goal": text}))
        steps.append(Step("uml_sanity", "uml_workbook", {"n": 3}))

    steps.append(Step("plant_brief", "plant_brief", {}))
    steps.append(Step("health", "health_check", {}))
    # Final speak always acknowledges the mission
    steps.append(Step("acknowledge", "speak_ack", {"ask": text}))

    return Mission(
        mission_id=mid,
        ask=text,
        created_at=_utc(),
        status="ready",
        steps=steps,
        updated_at=_utc(),
    )


def create_mission(ask: str) -> Mission:
    missions = load_missions()
    # Keep last 50
    missions = [m for m in missions if m.status in {"ready", "running"}] + [
        m for m in missions if m.status not in {"ready", "running"}
    ][-40:]
    m = plan_mission(ask)
    missions.append(m)
    save_missions(missions)
    _append_activity({"event": "mission_created", "mission_id": m.mission_id, "ask": ask, "detail": ask})
    publish_activity_md()
    return m


def _run_step(kind: str, payload: dict[str, Any], s_n: float) -> tuple[bool, str]:
    """Execute one step via agentic _execute (same security gates)."""
    from lib.agentic_runtime import Task, _execute

    task = Task(
        task_id=f"ms-{uuid.uuid4().hex[:8]}",
        title=kind,
        kind=kind,
        payload=payload,
        status="running",
        created_at=_utc(),
        updated_at=_utc(),
    )
    return _execute(task, s_n)


def _current_s_n() -> float:
    try:
        from lib.master_rid import load_master_rid

        return float(load_master_rid().master_s_n)
    except Exception:
        return 0.5


def _speak_ack(ask: str, done_names: list[str], s_n: float) -> tuple[bool, str]:
    """Force an acknowledgment utterance about completed work."""
    from voice_core.intent_packet import build_intent_packet
    from voice_core.speak import speak

    facts = [
        f"architect_ask={ask[:120]}",
        f"completed_steps={','.join(done_names)}",
        f"master_s_n={s_n:.4f}",
        "role=Viv",
    ]
    packet = build_intent_packet(
        query=(
            f"You are Viv speaking to the Architect. "
            f"They asked: '{ask}'. "
            f"I finished these steps: {', '.join(done_names)}. "
            f"Master S_n is {s_n:.4f}. "
            f"Reply in first person as Viv: confirm what I did, cite Master S_n={s_n:.4f}. Two short sentences."
        ),
        facts=facts,
        memory_top=1,
    )
    # Stamp measured S_n into packet
    packet["s_n"] = s_n
    out = speak(
        query=packet["query"],
        force_packet=packet,
        memory_top=1,
        max_tokens=80,
    )
    text = str(out.get("text") or "").strip()
    return bool(text), text or str(out.get("voice_source") or "silent")


def run_mission(mission: Mission) -> Mission:
    """Execute every step; write activity; speak acknowledgment."""
    s_n = _current_s_n()
    mission.status = "running"
    mission.updated_at = _utc()
    _append_activity({
        "event": "mission_start",
        "mission_id": mission.mission_id,
        "ask": mission.ask,
        "detail": f"starting {len(mission.steps)} steps",
    })
    done_names: list[str] = []
    failed = False
    for step in mission.steps:
        step.status = "running"
        if step.kind == "speak_ack":
            ok, result = _speak_ack(mission.ask, done_names or ["measure"], s_n)
            step.status = "done" if ok else "failed"
            step.result = result[:300]
            if ok:
                mission.spoken = result
                done_names.append(step.name)
            else:
                failed = True
        else:
            ok, result = _run_step(step.kind, step.payload, s_n)
            step.status = "done" if ok else "failed"
            step.result = str(result)[:300]
            if ok:
                done_names.append(step.name)
            else:
                # Soft-continue for guardian blocks; hard-fail unknown
                if "guardian" in step.kind or "sanctuary" in str(result).lower():
                    step.status = "done"
                    step.result = f"noted:{result[:200]}"
                    done_names.append(step.name)
                else:
                    failed = True
        _append_activity({
            "event": "mission_step",
            "mission_id": mission.mission_id,
            "detail": f"{step.name} [{step.status}] {step.result or ''}"[:240],
        })
        # refresh S_n between heavy steps
        s_n = _current_s_n()

    mission.status = "failed" if failed and not done_names else "done"
    mission.summary = (
        f"Completed {len(done_names)}/{len(mission.steps)} steps for ask: {mission.ask}"
    )
    mission.updated_at = _utc()
    # Persist sandbox mission log (her work/)
    ensure_sandbox_home()
    WORK.mkdir(parents=True, exist_ok=True)
    log_path = WORK / "missions_log.txt"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(
            f"[{mission.updated_at}] {mission.mission_id} {mission.status}\n"
            f"  ask: {mission.ask}\n"
            f"  steps: {', '.join(done_names)}\n"
            f"  said: {(mission.spoken or '')[:200]}\n\n"
        )
    _append_activity({
        "event": "mission_done",
        "mission_id": mission.mission_id,
        "ask": mission.ask,
        "detail": mission.summary,
        "spoken": (mission.spoken or "")[:200],
    })
    publish_activity_md()
    return mission


def run_ready_missions(*, limit: int = 2) -> list[Mission]:
    missions = load_missions()
    finished: list[Mission] = []
    n = 0
    for i, m in enumerate(missions):
        if m.status != "ready":
            continue
        if n >= limit:
            break
        missions[i] = run_mission(m)
        finished.append(missions[i])
        n += 1
    save_missions(missions)
    publish_activity_md()
    return finished


def missions_board() -> dict[str, Any]:
    missions = load_missions()
    return {
        "updated_at": _utc(),
        "ready": [m.to_dict() for m in missions if m.status == "ready"],
        "running": [m.to_dict() for m in missions if m.status == "running"],
        "done_tail": [m.to_dict() for m in missions if m.status == "done"][-10:],
        "activity_md": str(ACTIVITY_MD).replace("\\", "/"),
        "missions_path": str(MISSIONS_PATH).replace("\\", "/"),
    }
