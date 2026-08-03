"""Autonomous AIOS operator — foundation-gated pulse, piston, optional runtime tick."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.auto_gate import foundation_gate
from lib.auto_narrator import narrate_latest
from lib.auto_rid_journal import journal_pulse
from lib.autonomy_gate import (
    ensure_runtime_ready,
    evaluate_tiered_gate,
    runtime_needs_resume,
    write_autonomous_state,
)
from lib.cpu_status import format_pulse_line, format_pulse_message, pulse_payload
from lib.paths import AUTO_ARTIFACTS
from lib.security_membrane import filter_egress, heartbeat_stamp, require_membrane
from lib.master_rid import compute_master_rid, publish_master_rid
from lib.piston_background import (
    piston_background_running,
    read_piston_snapshot,
    start_piston_background,
    stop_piston_background,
)
from lib.autonomous_session_log import (
    AutonomousSessionLog,
    SESSION_LOG_JSONL,
    SESSION_LOG_PATH,
    format_beat_terminal_line,
)
from lib.plant_piston_bridge import LAST_CAPTURE_PATH
from lib.rid_feed import LIVE_SAMPLE_PATH, pulse_once


def _plant_snapshot() -> dict[str, Any]:
    if not LAST_CAPTURE_PATH.is_file():
        return {"published": False}
    try:
        data = json.loads(LAST_CAPTURE_PATH.read_text(encoding="utf-8"))
        v = data.get("verdict", {})
        return {
            "published": True,
            "verdict": v.get("verdict"),
            "csv": v.get("csv_path"),
            "cpu_load_max_pct": v.get("cpu_load_max_pct"),
            "published_at": data.get("published_at"),
        }
    except (json.JSONDecodeError, OSError):
        return {"published": False, "error": "read_failed"}


def autonomous_beat(
    *,
    pulse_path: Path,
    journal: bool = True,
    narrate: bool = True,
    piston: bool = True,
    runtime_tick: bool = False,
    max_tasks: int = 1,
) -> dict[str, Any]:
    """One autonomous cycle. Foundation fail -> halted without side effects."""
    pre = evaluate_tiered_gate()
    report: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": pre["mode"],
        "steps": [],
    }

    if not pre.get("allow_pulse"):
        report["steps"].append("halted_pre")
        report["gate"] = pre
        report["line"] = f"[AUTONOMY] HALTED — {pre.get('reasons')}"
        write_autonomous_state(report)
        return report

    membrane_halt = require_membrane()
    if membrane_halt:
        report["steps"].append("halted_security_membrane")
        report["security"] = membrane_halt
        report["gate"] = pre
        report["mode"] = "halted"
        report["line"] = f"[AUTONOMY] HALTED — {membrane_halt['reason']}"
        write_autonomous_state(report)
        return report

    sample = pulse_once()
    master = compute_master_rid(sample)
    publish_master_rid(master)
    payload = pulse_payload(sample, master)
    report["sample"] = sample.to_dict()
    report["steps"].append("pulse")

    if journal:
        j = journal_pulse(sample)
        payload["journal"] = j["heartbeat"]
        report["supervisor_control"] = j["supervisor"]["system_rid"]["control"]
        report["steps"].append("journal")

    if piston:
        p = read_piston_snapshot()
        payload["piston"] = p
        report["piston"] = p
        report["steps"].append("piston_snapshot")
        master = compute_master_rid(sample)
        publish_master_rid(master)
        payload.update(
            {
                "s_n": master.master_s_n,
                "master_s_n": master.master_s_n,
                "rsr": master.master_rsr,
                "ltp": master.master_ltp,
                "rle": master.master_rle,
                "master_rid": master.to_dict(),
                "subsystems": {k: v.to_dict() for k, v in master.subsystems.items()},
                "status": master.status,
                "line": format_pulse_line(sample, master),
                "message": format_pulse_message(sample, master),
            }
        )

    payload["plant"] = _plant_snapshot()
    report["plant"] = payload["plant"]

    master = compute_master_rid(sample)
    s_n = master.master_s_n
    report["security"] = heartbeat_stamp(s_n)

    if narrate:
        n = narrate_latest(print_line=False, s_n=s_n)
        if n.get("line"):
            report["narrator_line"] = n["line"]
        report["steps"].append("narrator")

    if report.get("narrator_line"):
        filtered, ev = filter_egress(report["narrator_line"], s_n)
        if ev and not ev.get("allowed"):
            report["narrator_line"] = filtered
            report["security_egress_narrator"] = ev
            report["steps"].append("security_egress_narrator")

    msg = payload.get("message") or format_pulse_message(sample, master)
    filtered_msg, ev_msg = filter_egress(msg, s_n)
    payload["message"] = filtered_msg
    if ev_msg and not ev_msg.get("allowed"):
        report["security_egress_message"] = ev_msg
        report["steps"].append("security_egress_message")

    payload["security_membrane"] = report["security"]

    pulse_path.parent.mkdir(parents=True, exist_ok=True)
    pulse_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report["steps"].append("artifact")

    post = evaluate_tiered_gate(
        sample_s_n=master.master_s_n,
        sample_status=master.status,
    )
    report["gate"] = post
    report["mode"] = post["mode"]
    report["steps"].append("gate")

    if runtime_tick and post.get("allow_runtime"):
        resume_info = ensure_runtime_ready()
        if resume_info.get("resumed"):
            report["runtime_resume"] = resume_info
        from lib.auto_run import runtime_tick

        report["runtime_tick"] = runtime_tick(max_tasks)
        report["steps"].append("runtime_tick")
    elif runtime_tick:
        report["runtime_tick"] = {"skipped": True, "reason": post.get("reasons")}

    # CPU-first RID tick (no GPU) — always try when pulse allowed
    if post.get("allow_pulse"):
        try:
            from lib.cpu_rid_tick import rid_cpu_tick

            report["cpu_rid_tick"] = rid_cpu_tick(settle_s=1.5)
            report["steps"].append("cpu_rid_tick")
        except Exception as exc:  # noqa: BLE001
            report["cpu_rid_tick"] = {"ok": False, "reason": str(exc)}

    report["line"] = format_pulse_line(sample, master)
    report["master_s_n"] = master.master_s_n
    report["master_rid"] = master.to_dict()
    report["allow_runtime"] = bool(post.get("allow_runtime"))

    if post.get("allow_pulse") and s_n >= 0.15:
        try:
            from lib.carma_memory import append_live_note

            rt = report.get("runtime_tick") or {}
            rt_ok = rt.get("ok") if isinstance(rt, dict) else None
            note = (
                f"autonomous beat mode={post.get('mode')} s_n={s_n:.3f} "
                f"control={report.get('supervisor_control')} rt_ok={rt_ok}"
            )
            mem = append_live_note(note, s_n=s_n)
            report["memory_live"] = mem
            if mem.get("ok"):
                report["steps"].append("memory_live")
        except Exception as exc:  # noqa: BLE001
            report["memory_live"] = {"ok": False, "reason": str(exc)}

    # Optional autonomous speak (GPU/LoRA) — cadence from cpu_config
    try:
        from lib.paths import FOUNDATION_ROOT

        cfg_path = FOUNDATION_ROOT / "cpu_config.json"
        voice_cfg = {}
        autonomy_cfg = {}
        if cfg_path.is_file():
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            voice_cfg = dict(raw.get("voice") or {})
            autonomy_cfg = dict(raw.get("autonomy") or {})
        if autonomy_cfg.get("voice_speak", True) and not voice_cfg.get("deferred", False):
            every = max(1, int(voice_cfg.get("speak_every_n_beats") or 30))
            min_sn = float(voice_cfg.get("speak_min_s_n") or 0.45)
            # Persist beat counter on autonomous state file sibling
            from lib.paths import AUTO_ARTIFACTS

            ctr_path = AUTO_ARTIFACTS / "voice_speak_counter.json"
            ctr = {"beats": 0}
            if ctr_path.is_file():
                try:
                    ctr = json.loads(ctr_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    ctr = {"beats": 0}
            beats = int(ctr.get("beats") or 0) + 1
            ctr_path.write_text(json.dumps({"beats": beats, "every": every}, indent=2), encoding="utf-8")
            if s_n >= min_sn and beats % every == 0:
                from lib.voice_bridge import speak as viv_speak

                sp = viv_speak("state summary", memory_top=2, max_tokens=64)
                report["voice_speak"] = {
                    "ok": sp.get("ok"),
                    "source": sp.get("voice_source"),
                    "text": (sp.get("text") or "")[:280],
                    "beat": beats,
                }
                if sp.get("text"):
                    report["steps"].append("voice_speak")
                    report["voice_line"] = sp.get("text")
    except Exception as exc:  # noqa: BLE001
        report["voice_speak"] = {"ok": False, "reason": str(exc)}

    write_autonomous_state(report)
    return report


def autonomous_loop(
    *,
    interval: float = 1.0,
    pulse_path: Path | None = None,
    journal: bool = True,
    narrate: bool = False,
    piston: bool = True,
    runtime_tick: bool = True,
    max_tasks: int = 1,
    max_beats: int = 0,
    session_log_path: Path | None = None,
) -> int:
    """Run autonomous operator until Ctrl+C or max_beats."""
    out = pulse_path or (AUTO_ARTIFACTS / "pulse.json")
    fg = foundation_gate(include_stress=False)
    piston_bg = False
    if piston:
        piston_bg = start_piston_background(interval=max(0.5, interval), journal=False)

    session = AutonomousSessionLog(session_log_path)
    session.start(
        config={
            "interval": interval,
            "journal": journal,
            "narrate": narrate,
            "piston": piston,
            "runtime_tick": runtime_tick,
            "max_tasks": max_tasks,
            "max_beats": max_beats,
            "pulse_path": str(out),
            "session_log_path": str(session.path),
        },
        startup={
            "foundation_gate": fg,
            "piston_background": piston_bg,
        },
    )

    def _log_print(text: str) -> None:
        print(text)
        session.terminal(text)

    _log_print("=== AIOS autonomous operator ===")
    _log_print(f"  foundation_gate: {'OK' if fg.get('allow') else 'FAIL'}")
    resume_info = ensure_runtime_ready()
    if resume_info.get("resumed"):
        _log_print("  agentic_runtime: auto-resumed")
    elif runtime_needs_resume():
        _log_print("  agentic_runtime: PAUSED (requires resume)")
    session.record_startup(resume_info=resume_info)
    _log_print(f"  interval:        {interval}s")
    _log_print(f"  live_sample:     {LIVE_SAMPLE_PATH}")
    _log_print(f"  pulse:           {out}")
    _log_print(f"  state:           {AUTO_ARTIFACTS / 'autonomous_state.json'}")
    _log_print(f"  session_log:     {session.path}")
    _log_print(f"  session_jsonl:   {SESSION_LOG_JSONL}")
    _log_print(
        f"  piston:          {'background' if piston_bg else ('off' if not piston else 'stale')}  "
        f"runtime_tick: {runtime_tick}"
    )
    from lib.security_membrane import membrane_status

    membrane = membrane_status()
    session.record_startup(security_membrane=membrane)
    _log_print(f"  security_membrane: {'ARMED' if membrane.get('armed') else 'MISSING'}")
    _log_print("  Ctrl+C to stop.")
    beats = 0
    stop_reason = "unknown"
    try:
        while True:
            try:
                beat = autonomous_beat(
                    pulse_path=out,
                    journal=journal,
                    narrate=narrate,
                    piston=piston,
                    runtime_tick=runtime_tick,
                    max_tasks=max_tasks,
                )
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                msg = f"[AUTONOMY] beat error (continuing): {exc}"
                print(msg, file=sys.stderr)
                session.terminal(msg, stream="stderr")
                session.error(msg)
                beats += 1
                time.sleep(interval)
                continue
            terminal_line = format_beat_terminal_line(beat)
            print(terminal_line)
            beats += 1
            session.beat(beat_no=beats, terminal_line=terminal_line, report=beat)
            if max_beats > 0 and beats >= max_beats:
                stop_reason = "max_beats"
                _log_print(f"max_beats={max_beats} reached.")
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
        print(f"\nstopped after {beats} beats.")
        session.terminal(f"stopped after {beats} beats.")
    finally:
        extra: dict[str, Any] = {}
        if piston and piston_background_running():
            bg_beats = stop_piston_background()
            msg = f"  piston background stopped ({bg_beats} ticks)"
            print(msg)
            session.terminal(msg)
            extra["piston_background_ticks"] = bg_beats
        session.shutdown(reason=stop_reason, beats=beats, extra=extra or None)
    return 0
