"""AIOS organism — one mind, one beat, all pillars.

This is the sovereign integration layer. RID + agentic + CPU teach + UML +
optional Qwen voice run as one organism, not disconnected CLIs.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.agentic_runtime import (
    ensure_cpu_work_queue,
    enqueue,
    load_queue,
    load_state,
    needs_resume,
    resume,
    run_once as agentic_run_once,
    status as agentic_status,
)
from lib.autonomous_operator import autonomous_beat
from lib.autonomy_gate import evaluate_tiered_gate
from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT
from lib.security_membrane import membrane_status, require_membrane

ORGANISM_ROOT = AUTO_ARTIFACTS / "organism"
ORGANISM_STATE = ORGANISM_ROOT / "organism_state.json"
ORGANISM_EVENTS = ORGANISM_ROOT / "organism_events.jsonl"
ORGANISM_LATEST = ORGANISM_ROOT / "latest_beat.json"
HALT_FLAG = AUTO_ARTIFACTS / "halt.flag"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _append_event(event: dict[str, Any]) -> None:
    ORGANISM_ROOT.mkdir(parents=True, exist_ok=True)
    row = dict(event)
    row.setdefault("timestamp", _utc())
    with ORGANISM_EVENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _load_cpu_config() -> dict[str, Any]:
    path = FOUNDATION_ROOT / "cpu_config.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _foundation_health() -> dict[str, Any]:
    try:
        from lib.foundation_health import evaluate_foundation_gate

        return evaluate_foundation_gate(include_stress=False)
    except Exception:
        try:
            from lib.auto_gate import foundation_gate

            return foundation_gate(include_stress=False)
        except Exception as exc:  # noqa: BLE001
            return {"allow": False, "ok": False, "error": str(exc)}


def seed_curriculum(*, force: bool = False) -> dict[str, Any]:
    """Keep the mind busy: dream, code, health, UML, RID, memory, journal."""
    tasks = load_queue()
    ready = [t for t in tasks if t.status == "ready"]
    if ready and not force:
        fill = ensure_cpu_work_queue()
        return {"seeded": 0, "ready": len(ready), "cpu_autofill": fill, "reason": "already_ready"}

    added: list[str] = []
    specs = [
        ("dream_cycle", "REM dream consolidation", 5, {"force": True}),
        ("sandbox_code", "Write+run sandbox tool", 6, {}),
        ("health_check", "Membrane health", 10, {}),
        ("uml_workbook", "UML practice workbook", 15, {"n": 3}),
        ("rid_sample", "Live RID sample publish", 20, {}),
        ("guardian_pulse", "Guardian tariff pulse", 25, {}),
        ("plant_brief", "Write plant brief", 28, {}),
        ("append_journal", "Organism journal line", 30, {"line": f"[{_utc()}] aios organism curriculum"}),
        ("memory_append", "Remember organism boot", 35, {
            "text": f"[{_utc()}] AIOS organism curriculum seeded — dream+code+CPU mind active",
            "provenance": "organism",
            "tags": ["aios", "organism", "cpu", "dream", "code"],
        }),
        ("cpu_rid_observe", "CPU RID hold observe A", 40, {"settle_s": 1.2}),
        ("cpu_rid_observe", "CPU RID hold observe B", 41, {"settle_s": 1.2}),
        ("cpu_core_survey", "Survey governed CPU core adapters", 42, {}),
        ("cpu_reasoning_probe", "Run CPU evidence-to-renderer reasoning probe", 43, {
            "value": "What does the Alpha manual say about CPU mind and GPU mouth?",
            "manual_only": True,
            "top_k": 3,
        }),
        ("cpu_choice_simulation", "Simulate bounded three-action CPU choice economy", 44, {
            "states": [
                {"s_n": 0.20, "memory_due": True, "queued_work": 0},
                {"s_n": 0.80, "memory_due": False, "queued_work": 1},
                {"s_n": 0.90, "memory_due": False, "queued_work": 0},
            ],
            "choices": ["restore", "action", "idle"],
            "max_steps": 3,
        }),
        ("voice_status", "Voice peripheral status", 50, {}),
        ("speak_brief", "Speak after curriculum", 55, {"query": "I dreamed, wrote code, and measured the plant"}),
    ]
    for kind, title, pri, payload in specs:
        t = enqueue(kind=kind, title=title, priority=pri, payload=payload, max_retries=1)
        added.append(t.task_id)
    _append_event({"event": "curriculum_seeded", "added": added, "count": len(added)})
    return {"seeded": len(added), "task_ids": added}


def boot(*, seed: bool = True, clear_halt: bool = False) -> dict[str, Any]:
    """Bring AIOS online: foundation, membrane, resume, curriculum, voice probe."""
    ORGANISM_ROOT.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "timestamp": _utc(),
        "ok": True,
        "steps": [],
        "pillars": {},
    }

    # Law 7: ensure her sandbox home exists + migrate flat junk
    try:
        from lib.aios_sandbox import ensure_sandbox_home, migrate_legacy_flat_files

        report["pillars"]["sandbox"] = ensure_sandbox_home()
        moved = migrate_legacy_flat_files()
        if moved:
            report["pillars"]["sandbox"]["migrated"] = moved
        report["steps"].append("sandbox_home")
    except Exception as exc:  # noqa: BLE001
        report["pillars"]["sandbox"] = {"ok": False, "error": str(exc)}

    if clear_halt and HALT_FLAG.is_file():
        HALT_FLAG.unlink()
        report["steps"].append("halt_cleared")

    if HALT_FLAG.is_file():
        report["ok"] = False
        report["halted"] = True
        report["reason"] = "halt.flag present — operator must clear or aios_main resume"
        _write_json(ORGANISM_STATE, report)
        return report

    fh = _foundation_health()
    report["pillars"]["foundation"] = {
        "allow": bool(fh.get("allow") or fh.get("ok")),
        "detail": fh.get("failed") or fh.get("checks") or fh.get("verdict"),
    }
    report["steps"].append("foundation")
    if not (fh.get("allow") or fh.get("ok")):
        report["ok"] = False
        report["reason"] = "foundation_denied"
        _write_json(ORGANISM_STATE, report)
        _append_event({"event": "boot_failed", "reason": "foundation"})
        return report

    halt = require_membrane()
    mem = membrane_status()
    report["pillars"]["security"] = {
        "armed": bool(mem.get("armed")),
        "halt": halt,
        "version": mem.get("version"),
    }
    report["steps"].append("security")
    if halt:
        report["ok"] = False
        report["reason"] = halt.get("reason") if isinstance(halt, dict) else str(halt)
        _write_json(ORGANISM_STATE, report)
        return report

    if needs_resume():
        report["pillars"]["agentic_resume"] = resume()
        report["steps"].append("resume")
    else:
        report["pillars"]["agentic_resume"] = {"resumed": False, "reason": "not_paused"}

    if seed:
        report["pillars"]["curriculum"] = seed_curriculum(force=False)
        report["steps"].append("curriculum")

    # Voice peripheral (optional)
    try:
        from voice_core.speak import speak_status

        vs = speak_status()
        report["pillars"]["voice"] = {
            "backend": vs.get("backend"),
            "served_name": vs.get("served_name"),
            "reachable": vs.get("reachable"),
            "gguf_ready": (vs.get("gguf") or {}).get("gguf_ready"),
        }
        report["steps"].append("voice")
    except Exception as exc:  # noqa: BLE001
        report["pillars"]["voice"] = {"ok": False, "error": str(exc)}

    # Live RID sample
    try:
        from lib.rid_feed import pulse_once
        from lib.master_rid import compute_master_rid, publish_master_rid

        sample = pulse_once()
        master = compute_master_rid(sample)
        publish_master_rid(master)
        report["pillars"]["rid"] = {
            "master_s_n": master.master_s_n,
            "status": master.status,
            "rsr": master.master_rsr,
            "ltp": master.master_ltp,
            "rle": master.master_rle,
        }
        report["steps"].append("rid")
    except Exception as exc:  # noqa: BLE001
        report["pillars"]["rid"] = {"ok": False, "error": str(exc)}
        report["ok"] = False

    # Real systems map — V1+V2 cores vs Viv
    try:
        from lib.aios_systems import write_registry

        sys_rep = write_registry()
        nxt = sys_rep.get("next") or {}
        report["pillars"]["systems"] = {
            "counts": sys_rep.get("counts"),
            "next": f"{nxt.get('generation')}/{nxt.get('id')}" if nxt.get("id") else None,
            "registry_md": sys_rep.get("registry_md"),
        }
        report["steps"].append("systems_registry")
    except Exception as exc:  # noqa: BLE001
        report["pillars"]["systems"] = {"ok": False, "error": str(exc)}

    cfg = _load_cpu_config()
    report["doctrine"] = {
        "cpu_first": True,
        "gpu_overnight": bool((cfg.get("prt") or {}).get("gpu_overnight_enabled")),
        "voice_speak": bool((cfg.get("autonomy") or {}).get("voice_speak")),
        "mode": cfg.get("mode"),
    }
    report["agentic"] = agentic_status()
    report["mode"] = "online" if report["ok"] else "degraded"
    _write_json(ORGANISM_STATE, report)
    _append_event({"event": "boot", "ok": report["ok"], "mode": report["mode"]})
    return report


def organism_beat(
    *,
    max_tasks: int = 2,
    speak: bool | None = None,
    narrate: bool = False,
) -> dict[str, Any]:
    """One full AIOS mind cycle: inbox → autonomy → agentic work → task board."""
    if HALT_FLAG.is_file():
        out = {"ok": False, "halted": True, "timestamp": _utc(), "reason": "halt.flag"}
        _write_json(ORGANISM_LATEST, out)
        return out

    # Operator channel first — new asks become missions at submit; drain audits inbox
    inbox_rep: dict[str, Any] = {"drained": 0}
    try:
        from lib.aios_inbox import drain_inbox, publish_task_board, report_outbox

        inbox_rep = drain_inbox(limit=20)
        if inbox_rep.get("drained"):
            _append_event({"event": "inbox_drained", **{k: inbox_rep[k] for k in ("drained", "missions") if k in inbox_rep}})
    except Exception as exc:  # noqa: BLE001
        inbox_rep = {"drained": 0, "error": str(exc)}

    # FULL missions — execute complete goal chains (not micro-MVP crumbs)
    missions_run: list[dict[str, Any]] = []
    try:
        from lib.aios_missions import run_ready_missions

        finished = run_ready_missions(limit=2)
        for m in finished:
            missions_run.append(
                {
                    "mission_id": m.mission_id,
                    "ask": m.ask,
                    "status": m.status,
                    "steps": [{"name": s.name, "status": s.status, "result": (s.result or "")[:120]} for s in m.steps],
                    "spoken": (m.spoken or "")[:280],
                    "summary": m.summary,
                }
            )
        if finished:
            _append_event({"event": "missions_run", "n": len(finished), "ids": [m.mission_id for m in finished]})
    except Exception as exc:  # noqa: BLE001
        missions_run = [{"error": str(exc)}]

    ensure_cpu_work_queue()
    # Curriculum only if no autonomy goal and queue thin
    ready_n = sum(1 for t in load_queue() if t.status == "ready")
    try:
        from lib.aios_missions import load_missions
        from lib.aios_goals import list_goals

        mission_ready = sum(1 for m in load_missions() if m.status == "ready")
        goal_active = len(list_goals(status="active"))
    except Exception:
        mission_ready = 0
        goal_active = 0
    if ready_n < 2 and mission_ready == 0 and goal_active == 0:
        seed_curriculum(force=True)

    cfg = _load_cpu_config()
    autonomy = cfg.get("autonomy") or {}
    life_beat = 0
    try:
        if ORGANISM_STATE.is_file():
            prev = json.loads(ORGANISM_STATE.read_text(encoding="utf-8"))
            life_beat = int((prev.get("life_beat") or 0)) + 1
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        life_beat = 1

    # LEVEL 3 AGENT: perceive → reason → act → learn (primary beat owner)
    agent_rep: dict[str, Any] | None = None
    dream_rep: dict[str, Any] | None = None
    code_rep: dict[str, Any] | None = None
    self_rep: dict[str, Any] | None = None
    try:
        from lib.aios_agent import agent_cycle

        agent_rep = agent_cycle()
        _append_event(
            {
                "event": "agent_cycle",
                "decision": ((agent_rep.get("reason") or {}).get("decision")),
                "step": ((agent_rep.get("reason") or {}).get("step")),
                "act_ok": ((agent_rep.get("act") or {}).get("ok")),
                "goal_id": ((agent_rep.get("perceive") or {}).get("goal_id")),
            }
        )
        kind = ((agent_rep.get("reason") or {}).get("kind")) or ""
        if kind == "dream":
            dream_rep = {
                "ok": ((agent_rep.get("act") or {}).get("ok")),
                "stdout": ((agent_rep.get("act") or {}).get("stdout")),
            }
        elif kind in {"ensure_tools", "sandbox_health", "plant_brief"}:
            code_rep = {
                "ok": ((agent_rep.get("act") or {}).get("ok")),
                "stdout": ((agent_rep.get("act") or {}).get("stdout")),
            }
    except Exception as exc:  # noqa: BLE001
        agent_rep = {"ok": False, "error": str(exc)}

    # Legacy self-life OFF by default (0). Enable only via cpu_config if debugging.
    self_every = int(autonomy.get("self_life_every_n_beats") or 0)
    if self_every > 0 and (life_beat == 1 or life_beat % self_every == 0):
        try:
            from lib.aios_self import self_life_cycle

            self_rep = self_life_cycle(speak=False)
        except Exception as exc:  # noqa: BLE001
            self_rep = {"ok": False, "error": str(exc)}

    gate = evaluate_tiered_gate()
    sn_pre = 0.0
    try:
        from lib.master_rid import load_master_rid

        sn_pre = float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        sn_pre = 0.0

    beat = autonomous_beat(
        pulse_path=AUTO_ARTIFACTS / "pulse.json",
        journal=True,
        narrate=narrate,
        piston=True,
        runtime_tick=bool(gate.get("allow_runtime")),
        max_tasks=max(1, max_tasks),
    )

    agent_decision = ((agent_rep or {}).get("reason") or {}).get("decision")
    agentic_rep = None
    if (
        gate.get("allow_pulse")
        and not load_state().get("requires_operator_resume")
        and not missions_run
        and agent_decision != "act"
    ):
        agentic_rep = agentic_run_once(max_tasks=max(1, max_tasks))
        beat["agentic"] = agentic_rep
        beat.setdefault("steps", []).append("agentic")

    # Speak: agent progress first; if Architect enabled voice_speak, cadence speak too
    agent_said = (agent_rep or {}).get("spoken") or ""
    voice_cfg = (cfg.get("voice") or {}) if isinstance(cfg, dict) else {}
    allow_speak = bool(autonomy.get("voice_speak"))
    sn_now = float(beat.get("master_s_n") or sn_pre or 0.0)
    min_sn = float(voice_cfg.get("speak_min_s_n") or 0.42)
    every = max(1, int(voice_cfg.get("speak_every_n_beats") or 5))

    if agent_said:
        beat["voice_speak"] = {
            "ok": True,
            "source": "cpu_honest+agent",
            "text": agent_said[:280],
            "from": "agent_cycle",
        }
        beat.setdefault("steps", []).append("voice_speak")
    elif allow_speak and sn_now >= min_sn and (life_beat % every == 0):
        try:
            from lib.voice_bridge import speak as viv_speak

            intent = (
                f"Progress beat {life_beat}. "
                f"decision={((agent_rep or {}).get('reason') or {}).get('decision')} "
                f"step={((agent_rep or {}).get('reason') or {}).get('step')} "
                f"S_n={sn_now:.3f}"
            )
            sp = viv_speak(intent, memory_top=2, max_tokens=64)
            beat["voice_speak"] = {
                "ok": sp.get("ok"),
                "source": sp.get("voice_source") or "voice_bridge",
                "text": (sp.get("text") or "")[:280],
                "from": "cadence",
            }
            if sp.get("text"):
                beat.setdefault("steps", []).append("voice_speak")
        except Exception as exc:  # noqa: BLE001
            beat["voice_speak"] = {"ok": False, "reason": str(exc), "text": ""}
    else:
        beat["voice_speak"] = {
            "ok": True,
            "skipped": "no_agent_speech" if not allow_speak else "cadence_wait",
            "text": "",
        }

    out = {
        "timestamp": _utc(),
        "ok": True,
        "mode": beat.get("mode"),
        "master_s_n": beat.get("master_s_n"),
        "steps": beat.get("steps"),
        "cpu_rid_tick": beat.get("cpu_rid_tick"),
        "runtime_tick": beat.get("runtime_tick"),
        "agentic": agentic_rep,
        "inbox": inbox_rep,
        "missions_run": missions_run,
        "agent": agent_rep,
        "self_life": self_rep,
        "dream": dream_rep,
        "sandbox_code": code_rep,
        "life_beat": life_beat,
        "voice_speak": beat.get("voice_speak"),
        "line": beat.get("line"),
        "allow_runtime": beat.get("allow_runtime"),
    }

    try:
        from lib.aios_inbox import publish_task_board, report_outbox

        board = publish_task_board(beat=out)
        out["task_board"] = {
            "counts": board.get("counts"),
            "ready": len(board.get("ready") or []),
            "path": str(ORGANISM_ROOT / "task_board.md").replace("\\", "/"),
            "activity": "L:/Continue/Viv/foundation/artifacts/auto/organism/ACTIVITY.md",
        }
        if missions_run:
            report_outbox("missions_complete", missions=missions_run)
        if agent_rep:
            report_outbox("agent_cycle", agent=agent_rep)
        out.setdefault("steps", []).append("task_board")
    except Exception as exc:  # noqa: BLE001
        out["task_board"] = {"ok": False, "error": str(exc)}

    _write_json(ORGANISM_LATEST, out)
    _append_event(
        {
            "event": "beat",
            "master_s_n": out.get("master_s_n"),
            "mode": out.get("mode"),
            "missions": len(missions_run),
            "agent_decision": agent_decision,
            "cpu_label": (out.get("cpu_rid_tick") or {}).get("label"),
            "life_beat": life_beat,
        }
    )
    state = {
        "updated_at": _utc(),
        "mode": out.get("mode"),
        "master_s_n": out.get("master_s_n"),
        "life_beat": life_beat,
        "last_beat": out,
        "agentic": agentic_status(),
        "online": True,
        "task_board": out.get("task_board"),
    }
    _write_json(ORGANISM_STATE, state)
    return out


def _ascii(s: str, n: int = 240) -> str:
    return (s or "").encode("ascii", errors="replace").decode("ascii")[:n]


def _print_beat(n: int, beat: dict[str, Any]) -> None:
    """Operator-visible beat — goal / step / act / learn / handoff."""
    sn = beat.get("master_s_n")
    cpu = (beat.get("cpu_rid_tick") or {}).get("label")
    print(f"\n[AIOS #{n}] S_n={sn}  plant_cpu={cpu}  mode={beat.get('mode')}  life={beat.get('life_beat')}")

    agent = beat.get("agent") or {}
    if agent:
        perc = agent.get("perceive") or {}
        reason = agent.get("reason") or {}
        act = agent.get("act") or {}
        learn = agent.get("learn") or {}
        if perc.get("objective"):
            print(f"  GOAL: {_ascii(str(perc.get('objective')), 160)} ({perc.get('goal_id')})")
        decision = reason.get("decision")
        if decision == "act":
            print(f"  STEP: {reason.get('step')} kind={reason.get('kind')}")
            if act.get("ok"):
                print(f"  ACT ok: {_ascii(str(act.get('stdout') or ''), 160)}")
            else:
                print(f"  ACT fail: {_ascii(str(act.get('error') or act.get('stdout') or ''), 160)}")
            if learn.get("adapted"):
                print("  LEARN: adapted (replan/heal)")
        elif decision == "handoff":
            print(f"  HANDOFF: {reason.get('reason')}")
        elif decision == "done":
            print("  DONE: goal plan complete")
        elif decision == "idle":
            print(f"  IDLE: {reason.get('reason')}")
        if agent.get("spoken"):
            print(f"  SAID (agent): {_ascii(str(agent.get('spoken')), 220)}")
        if agent.get("error"):
            print(f"  AGENT FAIL: {_ascii(str(agent.get('error')), 160)}")

    for m in beat.get("missions_run") or []:
        if m.get("error"):
            print(f"  MISSION ERROR: {_ascii(str(m.get('error')), 120)}")
            continue
        print(f"  MISSION [{m.get('status')}] {_ascii(str(m.get('ask')), 120)}")
        if m.get("spoken"):
            print(f"  SAID: {_ascii(str(m.get('spoken')), 240)}")

    voice = beat.get("voice_speak") or {}
    if (voice.get("text") or "").strip() and not (agent.get("spoken") or "").strip():
        if not any(m.get("spoken") for m in (beat.get("missions_run") or [])):
            print(f"  SAID ({voice.get('source')}): {_ascii(str(voice.get('text')), 220)}")

    board = beat.get("task_board") or {}
    if board.get("path"):
        print(f"  BOARD: {board.get('path')}")


def organism_run(
    *,
    interval_s: float = 2.0,
    max_beats: int | None = None,
    max_tasks: int = 2,
    speak_every: int = 5,
) -> int:
    """Continuous organism loop. Ctrl+C or halt.flag stops."""
    boot_rep = boot(seed=True)
    if not boot_rep.get("ok"):
        print(json.dumps(boot_rep, indent=2, default=str))
        return 2
    print(f"[AIOS] online  S_n={((boot_rep.get('pillars') or {}).get('rid') or {}).get('master_s_n')}")
    print(f"[AIOS] voice={((boot_rep.get('pillars') or {}).get('voice') or {}).get('served_name')}")
    print(f"[AIOS] sandbox={((boot_rep.get('pillars') or {}).get('sandbox') or {}).get('root') or 'L:/Continue/Viv/sandbox/'}")
    print("[AIOS] Level-3 ABSORB loop (legacy) — NOT the living PRT system.")
    print("       Living AIOS: aios_main.py run  →  PRT autonomous")
    print("       This path: systems absorb / missions only")
    print(f"[AIOS] loop interval={interval_s}s  Ctrl+C to stop")

    n = 0
    try:
        while True:
            if HALT_FLAG.is_file():
                print("[AIOS] halt.flag — stopping")
                break
            force_speak = speak_every > 0 and (n % speak_every == 0)
            beat = organism_beat(max_tasks=max_tasks, speak=force_speak)
            n += 1
            _print_beat(n, beat)
            if max_beats is not None and n >= max_beats:
                break
            time.sleep(max(0.5, float(interval_s)))
    except KeyboardInterrupt:
        print("\n[AIOS] interrupted")
    summary = {
        "timestamp": _utc(),
        "beats": n,
        "state_path": str(ORGANISM_STATE).replace("\\", "/"),
        "events_path": str(ORGANISM_EVENTS).replace("\\", "/"),
    }
    _append_event({"event": "run_stop", **summary})
    print(json.dumps(summary, indent=2))
    return 0


def status() -> dict[str, Any]:
    """Full organism dashboard."""
    out: dict[str, Any] = {
        "timestamp": _utc(),
        "halted": HALT_FLAG.is_file(),
        "organism_state": None,
        "latest_beat": None,
        "agentic": agentic_status(),
        "gate": evaluate_tiered_gate(),
    }
    if ORGANISM_STATE.is_file():
        try:
            out["organism_state"] = json.loads(ORGANISM_STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    if ORGANISM_LATEST.is_file():
        try:
            out["latest_beat"] = json.loads(ORGANISM_LATEST.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    try:
        from voice_core.speak import speak_status

        out["voice"] = speak_status()
    except Exception as exc:  # noqa: BLE001
        out["voice"] = {"error": str(exc)}
    try:
        from lib.master_rid import load_master_rid

        m = load_master_rid()
        out["rid"] = {
            "master_s_n": m.master_s_n,
            "status": m.status,
            "rsr": m.master_rsr,
            "ltp": m.master_ltp,
            "rle": m.master_rle,
        }
    except Exception as exc:  # noqa: BLE001
        out["rid"] = {"error": str(exc)}
    try:
        from lib.aios_systems import write_registry

        sys_rep = write_registry()
        out["systems"] = {
            "counts": sys_rep.get("counts"),
            "next": sys_rep.get("next"),
            "absorb_queue": (sys_rep.get("absorb_queue") or [])[:8],
            "registry_md": sys_rep.get("registry_md"),
        }
    except Exception as exc:  # noqa: BLE001
        out["systems"] = {"error": str(exc)}
    return out


def halt(reason: str = "operator_halt") -> dict[str, Any]:
    payload = {"reason": reason, "at": _utc(), "actor": "aios_main"}
    _write_json(HALT_FLAG, payload)
    _append_event({"event": "halt", **payload})
    return {"ok": True, "halted": True, **payload}


def clear_halt() -> dict[str, Any]:
    if HALT_FLAG.is_file():
        HALT_FLAG.unlink()
    return resume()
