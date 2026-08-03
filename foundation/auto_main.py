#!/usr/bin/env python3
"""
Viv foundation — Automation main (Vixi).

Single entry for Continue/automation + Viv agentic runtime (Rust-gated).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.auto_gate import evaluate_run_gate, foundation_gate
from lib.auto_narrator import narrate_latest
from lib.auto_rid_journal import EVENTS_PATH, HEARTBEAT_PATH, journal_pulse, read_supervisor_state
from lib.auto_run import run_beat, run_loop
from lib.autonomous_operator import autonomous_beat, autonomous_loop
from lib.autonomous_session_log import SESSION_LOG_PATH, AutonomousSessionLog, format_beat_terminal_line
from lib.paths import AUTO_ARTIFACTS, AUTOMATION_ROOT, FSAA_SCRIPTS
from lib.cpu_status import format_pulse_line, format_pulse_message, pulse_payload
from lib.master_rid import compute_master_rid, load_master_rid, publish_master_rid
from lib.rid_feed import LIVE_SAMPLE_PATH, feed_meta, pulse_once
from lib.triad_kernel import TRIAD_CONTRACT_VERSION

VERSION = "1.2.0"

HEARTBEAT_SCRIPT = AUTOMATION_ROOT / "master_ai_heartbeat_service.py"
HEALTH_SCRIPT = AUTOMATION_ROOT / "automation_health.py"
QUORUM_SCRIPT = AUTOMATION_ROOT / "aios_quorum_selftest.py"
RID_SELFTEST = AUTOMATION_ROOT / "3_body" / "rid_selftest.py"


def triad_descriptor() -> dict:
    """Stable Vixi policy contract consumed by the AIOS Triad kernel."""
    return {
        "pillar": "auto",
        "name": "Vixi",
        "version": VERSION,
        "triad_contract_version": TRIAD_CONTRACT_VERSION,
        "capabilities": ["decide", "authorize_capability", "authorize_egress"],
        "authority": "orchestration_not_security",
    }


def triad_decide(envelope: dict, *, rid: dict, uml: dict) -> dict:
    action = str(envelope.get("action") or "").strip().upper()
    allowed = bool(action) and bool(rid.get("allowed")) and bool(uml.get("allowed"))
    return {
        "allowed": allowed,
        "reason": "triad_inputs_valid" if allowed else "triad_input_denied",
        "action": action,
        "policy": "security_remains_authority",
    }


def triad_authorize_capability(
    *,
    operation: str,
    params: dict,
    context: dict,
    uml: dict,
) -> dict:
    del params
    envelope = context.get("envelope") or {}
    allowed = (
        bool(str(operation).strip())
        and bool(uml.get("allowed"))
        and bool((context.get("security_ingress") or {}).get("allowed"))
        and str(envelope.get("contract_version") or "") == TRIAD_CONTRACT_VERSION
    )
    return {
        "allowed": allowed,
        "reason": "capability_structurally_valid" if allowed else "capability_denied",
        "operation": str(operation),
    }


def triad_authorize_egress(*, result, context: dict, uml: dict) -> dict:
    del result
    allowed = bool(uml.get("allowed")) and bool(
        (context.get("security_ingress") or {}).get("allowed")
    )
    return {
        "allowed": allowed,
        "reason": "egress_ready_for_security" if allowed else "egress_pillar_denied",
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_py(script: Path, *args: str, cwd: Path | None = None) -> int:
    if not script.is_file():
        print(f"missing script: {script}", file=sys.stderr)
        return 2
    work = cwd or script.parent
    proc = subprocess.run([sys.executable, str(script), *args], cwd=str(work))
    return int(proc.returncode)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def cmd_heartbeat(args: argparse.Namespace) -> int:
    argv = []
    if args.once:
        argv.append("--once")
    if args.beat_seconds != 2.0:
        argv.extend(["--beat-seconds", str(args.beat_seconds)])
    return _run_py(HEARTBEAT_SCRIPT, *argv)


def cmd_health(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else AUTOMATION_ROOT
    return _run_py(HEALTH_SCRIPT, "--root", str(root))


def cmd_runtime(args: argparse.Namespace) -> int:
    from lib.agentic_runtime import QUEUE_PATH, STATE_PATH, run_once, status as agentic_status

    if args.action == "tick":
        report = run_once(max(1, args.max_tasks))
        print(json.dumps(report, indent=2, default=str))
        return 0 if report.get("ok") and int(report.get("exit_code", 0) or 0) == 0 else 1
    payload = {
        "timestamp": _utc_now(),
        "owner": "viv",
        "status": agentic_status(),
        "queue_path": str(QUEUE_PATH),
        "state_path": str(STATE_PATH),
        "queue": json.loads(QUEUE_PATH.read_text(encoding="utf-8")) if QUEUE_PATH.is_file() else {},
        "state": json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.is_file() else {},
    }
    out = Path(args.json) if args.json else AUTO_ARTIFACTS / "runtime_status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(out)
    ready = sum(1 for t in payload["queue"].get("tasks", []) if t.get("status") == "ready")
    print(f"ready_tasks={ready}")
    return 0


def cmd_foundation(args: argparse.Namespace) -> int:
    report = foundation_gate(include_stress=args.stress)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        tag = "OK" if report.get("allow") else "FAIL"
        print(f"foundation_gate={tag}")
        for item in report.get("checks", []):
            mark = "PASS" if item.get("ok") else "FAIL"
            print(f"  [{mark}] {item.get('name')}: {item.get('detail')}")
        print(f"artifact: {report.get('foundation_gate_path', AUTO_ARTIFACTS / 'foundation_gate.json')}")
    return 0 if report.get("allow") else 1


def cmd_check(args: argparse.Namespace) -> int:
    steps = [
        ("foundation", lambda: cmd_foundation(argparse.Namespace(stress=False, json=False))),
        ("pulse", lambda: cmd_pulse(argparse.Namespace(json="", quiet=True, allow_dormant=True, no_journal=False, piston=False))),
        ("gate", lambda: cmd_gate(argparse.Namespace(risk="low", irreversible=False, json=False))),
        ("narrator", lambda: cmd_narrator(argparse.Namespace(quiet=True, json=False))),
        ("guardian_demo", lambda: _run_py(_ROOT / "guardian_main.py", "demo")),
        ("health", lambda: cmd_health(argparse.Namespace(root=str(AUTOMATION_ROOT)))),
        ("quorum_selftest", lambda: _run_py(QUORUM_SCRIPT)),
        ("rid_selftest", lambda: _run_py(RID_SELFTEST)),
    ]
    report = {"timestamp": _utc_now(), "steps": []}
    rc = 0
    for name, fn in steps:
        code = fn()
        report["steps"].append({"name": name, "exit_code": code})
        if code != 0:
            rc = code
        print(f"[check] {name}: {'PASS' if code == 0 else 'FAIL'} ({code})")
    out = AUTO_ARTIFACTS / "check_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return rc


def _write_pulse_artifact(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _warn_deprecated(command: str, alternative: str) -> None:
    print(f"[DEPRECATED] auto_main.py {command} — use: {alternative}", file=sys.stderr)


def cmd_status(args: argparse.Namespace) -> int:
    from lib.plant_piston_bridge import LAST_CAPTURE_PATH
    from lib.piston_background import piston_background_running, read_piston_snapshot
    from lib.security_membrane import membrane_status

    payload: dict = {"pillar": "auto", "timestamp": _utc_now()}
    payload["security_membrane"] = membrane_status()
    for name, path in (
        ("pulse", AUTO_ARTIFACTS / "pulse.json"),
        ("autonomous_state", AUTO_ARTIFACTS / "autonomous_state.json"),
        ("autonomous_session", SESSION_LOG_PATH),
        ("master_rid", AUTO_ARTIFACTS / "master_rid.json"),
        ("foundation_gate", AUTO_ARTIFACTS / "foundation_gate.json"),
    ):
        if path.is_file():
            try:
                payload[name] = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                payload[name] = {"error": f"unreadable: {path}"}
    meta = feed_meta()
    payload["live_feed"] = {"path": str(meta.path), "age_s": meta.age_s, "fresh": meta.fresh}
    payload["supervisor"] = read_supervisor_state()
    payload["piston_background"] = piston_background_running()
    snap = read_piston_snapshot()
    if snap:
        payload["piston_snapshot"] = snap
    if LAST_CAPTURE_PATH.is_file():
        try:
            plant = json.loads(LAST_CAPTURE_PATH.read_text(encoding="utf-8"))
            payload["plant_verdict"] = plant.get("verdict")
        except (json.JSONDecodeError, OSError):
            payload["plant_verdict"] = None

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    master = payload.get("master_rid") or {}
    auto_st = payload.get("autonomous_state") or {}
    print(
        f"[AUTO] Master_S_n={master.get('master_s_n', '?')} "
        f"status={master.get('status', '?')} mode={auto_st.get('mode', '?')}"
    )
    print(f"  beats={auto_st.get('beat', '?')} piston_bg={payload['piston_background']}")
    feed = payload.get("live_feed") or {}
    print(f"  live_feed age_s={feed.get('age_s')} path={LIVE_SAMPLE_PATH}")
    verdict = (payload.get("plant_verdict") or {}).get("verdict")
    print(f"  plant_verdict={verdict or 'missing'}")
    sess = payload.get("autonomous_session") or {}
    print(f"  session_log={SESSION_LOG_PATH} status={sess.get('status', 'missing')} beats={sess.get('beats_completed', '?')}")
    sup = payload.get("supervisor") or {}
    rid = (sup.get("system_rid") or {})
    print(f"  supervisor_control={rid.get('control', '?')}")
    sec = payload.get("security_membrane") or {}
    print(f"  security_membrane={'ARMED' if sec.get('armed') else 'MISSING'}")
    print(f"\nRecommended loop: auto_main.py autonomous --interval 1")
    return 0


def cmd_pulse(args: argparse.Namespace) -> int:
    _warn_deprecated("pulse", "auto_main.py autonomous --once")
    sample = pulse_once()
    master = compute_master_rid(sample)
    publish_master_rid(master)
    payload = pulse_payload(sample, master)
    out = Path(args.json) if args.json else AUTO_ARTIFACTS / "pulse.json"
    if not args.no_journal:
        journal = journal_pulse(sample)
        payload["journal"] = journal["heartbeat"]
        payload["supervisor_control"] = journal["supervisor"]["system_rid"]["control"]
    if getattr(args, "piston", False):
        from lib.piston_engine import piston_pulse

        payload["piston"] = piston_pulse(journal=not args.no_journal)
        master = compute_master_rid(sample)
        publish_master_rid(master)
        payload.update(
            {
                "s_n": master.master_s_n,
                "master_s_n": master.master_s_n,
                "line": format_pulse_line(sample, master),
                "message": format_pulse_message(sample, master),
            }
        )
    _write_pulse_artifact(payload, out)
    if args.quiet:
        print(out)
    else:
        print(format_pulse_line(sample, master))
        print(payload["message"])
        if not args.no_journal:
            print(f"RID event logged | control={payload.get('supervisor_control')}")
        if payload.get("piston"):
            print(payload["piston"]["line"])
    return 0 if not payload["dormant"] or args.allow_dormant else 2


def cmd_loop(args: argparse.Namespace) -> int:
    _warn_deprecated("loop", "auto_main.py autonomous --interval 1")
    out = Path(args.json) if args.json else AUTO_ARTIFACTS / "pulse.json"
    print(f"CPU automaton @ {args.interval}s → {LIVE_SAMPLE_PATH} + {out}")
    if not args.no_journal:
        print(f"RID journal → {EVENTS_PATH}")
    if getattr(args, "piston", False):
        print("Piston-core per-core thermal control enabled")
    print("No LLM. RID physics only. Ctrl+C to stop.")
    try:
        while True:
            sample = pulse_once()
            master = compute_master_rid(sample)
            publish_master_rid(master)
            payload = pulse_payload(sample, master)
            if not args.no_journal:
                journal = journal_pulse(sample)
                payload["journal"] = journal["heartbeat"]
            if getattr(args, "piston", False):
                from lib.piston_engine import piston_pulse

                payload["piston"] = piston_pulse(journal=not args.no_journal)
                master = compute_master_rid(sample)
                publish_master_rid(master)
                payload["line"] = format_pulse_line(sample, master)
            _write_pulse_artifact(payload, out)
            line = format_pulse_line(sample, master)
            if not args.no_journal and payload.get("journal"):
                line += f" | ctl={payload['journal']['control']}"
            if payload.get("piston"):
                line += f" | {payload['piston']['line']}"
            print(line)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 0


def cmd_master(args: argparse.Namespace) -> int:
    if args.live:
        sample = pulse_once()
        master = compute_master_rid(sample)
        publish_master_rid(master)
    else:
        master = load_master_rid()
        if master is None:
            print("No master_rid.json — run pulse or autonomous first.", file=sys.stderr)
            return 2
    if args.json:
        print(json.dumps(master.to_dict(), indent=2))
    else:
        parts = " ".join(
            f"{k}={v.s_n:.4f}"
            for k, v in master.subsystems.items()
            if v.available
        )
        print(
            f"Master_S_n={master.master_s_n:.4f} ({master.status}) "
            f"RSR={master.master_rsr:.4f} LTP={master.master_ltp:.4f} RLE={master.master_rle:.4f}"
        )
        print(f"  subsystems: {parts}")
        print(f"  artifact: {AUTO_ARTIFACTS / 'master_rid.json'}")
    return 0


def cmd_supervisor(_: argparse.Namespace) -> int:
    state = read_supervisor_state()
    if state is None:
        print("No supervisor state yet. Run: auto_main pulse", file=sys.stderr)
        return 2
    rid = state.get("system_rid") or {}
    print(json.dumps(state, indent=2))
    print(
        f"control={rid.get('control')} verdict={rid.get('verdict')} "
        f"S_n={rid.get('s_n')}"
    )
    return 0


def cmd_rid_status(_: argparse.Namespace) -> int:
    meta = feed_meta()
    payload = {
        "live_sample": str(meta.path),
        "exists": meta.path.is_file(),
        "age_s": None if meta.age_s < 0 else round(meta.age_s, 3),
        "fresh": meta.fresh,
    }
    if meta.path.is_file():
        payload["sample"] = json.loads(meta.path.read_text(encoding="utf-8"))
    print(json.dumps(payload, indent=2))
    return 0


def cmd_narrator(args: argparse.Namespace) -> int:
    result = narrate_latest(print_line=not args.quiet)
    if args.json:
        print(json.dumps(result, indent=2))
    return 0 if result.get("rendered", 0) >= 0 else 1


def cmd_gate(args: argparse.Namespace) -> int:
    report = evaluate_run_gate(action_risk=args.risk, irreversible=args.irreversible)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        allow = report.get("allow")
        rid = report.get("rid_gate") or {}
        foundation = report.get("foundation_gate") or {}
        ftag = "OK" if foundation.get("allow") else "FAIL"
        print(
            f"gate={'ALLOW' if allow else 'DENY'} foundation={ftag} "
            f"control={rid.get('control')} s_n={rid.get('s_n')}"
        )
    return 0 if report.get("allow") else 30


def cmd_autonomous(args: argparse.Namespace) -> int:
    session_path = Path(args.session_log) if getattr(args, "session_log", "") else SESSION_LOG_PATH
    if args.once:
        session = AutonomousSessionLog(session_path)
        session.start(
            config={
                "once": True,
                "journal": not args.no_journal,
                "narrate": args.narrator,
                "piston": not args.no_piston,
                "runtime_tick": args.runtime_tick,
                "max_tasks": args.max_tasks,
                "pulse_path": str(Path(args.json) if args.json else AUTO_ARTIFACTS / "pulse.json"),
            },
            startup={"mode": "single_beat"},
        )
        beat = autonomous_beat(
            pulse_path=Path(args.json) if args.json else AUTO_ARTIFACTS / "pulse.json",
            journal=not args.no_journal,
            narrate=args.narrator,
            piston=not args.no_piston,
            runtime_tick=args.runtime_tick,
            max_tasks=args.max_tasks,
        )
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(beat, indent=2), encoding="utf-8")
        terminal_line = format_beat_terminal_line(beat)
        print(terminal_line)
        session.beat(beat_no=1, terminal_line=terminal_line, report=beat)
        if beat.get("runtime_tick"):
            rt_line = f"runtime_tick: {beat['runtime_tick']}"
            print(rt_line)
            session.terminal(rt_line)
        session.shutdown(reason="once", beats=1)
        return 0 if beat.get("mode") != "halted" else 1
    return autonomous_loop(
        interval=args.interval,
        pulse_path=Path(args.json) if args.json else None,
        journal=not args.no_journal,
        narrate=args.narrator,
        piston=not args.no_piston,
        runtime_tick=args.runtime_tick,
        max_tasks=args.max_tasks,
        max_beats=args.max_beats,
        session_log_path=session_path,
    )


def cmd_run(args: argparse.Namespace) -> int:
    _warn_deprecated("run", "auto_main.py autonomous --interval 1")
    if args.once:
        beat = run_beat(
            pulse_path=Path(args.json) if args.json else AUTO_ARTIFACTS / "pulse.json",
            journal=not args.no_journal,
            narrate=not args.no_narrator,
            runtime_tick=args.runtime_tick,
            max_tasks=args.max_tasks,
            piston=getattr(args, "piston", False),
        )
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(beat, indent=2), encoding="utf-8")
        if not args.quiet:
            print(beat.get("narrator_line") or beat.get("line"))
            if beat.get("piston"):
                print(beat["piston"]["line"])
            print(f"gate={'ALLOW' if beat.get('allow') else 'DENY'}")
        return 0 if beat.get("allow") or args.allow_denied else 30
    return run_loop(
        interval=args.interval,
        pulse_path=Path(args.json) if args.json else None,
        journal=not args.no_journal,
        narrate=not args.no_narrator,
        runtime_tick=args.runtime_tick,
        max_tasks=args.max_tasks,
        piston=getattr(args, "piston", False),
    )


def cmd_paths(_: argparse.Namespace) -> int:
    info = {
        "foundation": str(_ROOT),
        "automation": str(AUTOMATION_ROOT),
        "fsaa_scripts": str(FSAA_SCRIPTS),
        "artifacts_auto": str(AUTO_ARTIFACTS),
        "rid_events": str(AUTOMATION_ROOT / "3_body" / "rid_logs" / "events.jsonl"),
        "automaton_heartbeat": str(HEARTBEAT_PATH),
        "cpu_config": str(_ROOT / "cpu_config.json"),
        "guardian": str(_ROOT / "guardian_main.py"),
    }
    print(json.dumps(info, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="auto_main",
        description="Viv automation foundation — heartbeat, health, agentic runtime (Vixi).",
    )
    p.add_argument("--version", action="version", version=f"auto_main {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    hb = sub.add_parser("heartbeat", help="Master AI heartbeat gate (L:/Continue/automation)")
    hb.add_argument("--once", action="store_true")
    hb.add_argument("--beat-seconds", type=float, default=2.0)
    hb.set_defaults(func=cmd_heartbeat)

    hl = sub.add_parser("health", help="Automation tree health inventory")
    hl.add_argument("--root", default="", help="Automation root (default: Continue/automation)")
    hl.set_defaults(func=cmd_health)

    rt = sub.add_parser("runtime", help="Viv agentic runtime (Rust-gated)")
    rt.add_argument("action", choices=("status", "tick"), default="status", nargs="?")
    rt.add_argument("--max-tasks", type=int, default=3)
    rt.add_argument("--json", default="", help="Status JSON path")
    rt.set_defaults(func=cmd_runtime)

    sub.add_parser("check", help="Foundation + health + quorum + RID selftests").set_defaults(func=cmd_check)

    st = sub.add_parser("status", help="Read-only auto pillar status (Master S_n, plant, supervisor)")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_status)

    fd = sub.add_parser("foundation", help="Foundation bedrock gate (venv, plant, piston)")
    fd.add_argument("--stress", action="store_true", help="Include 2s subprocess stress burn")
    fd.add_argument("--json", action="store_true")
    fd.set_defaults(func=cmd_foundation)

    pl = sub.add_parser("pulse", help="One CPU automaton beat (RID + status, no LLM)")
    pl.add_argument("--json", default="", help="Pulse artifact path")
    pl.add_argument("--quiet", action="store_true", help="Only print artifact path")
    pl.add_argument("--no-journal", action="store_true", help="Skip automation rid_logs write")
    pl.add_argument("--allow-dormant", action="store_true", help="Exit 0 even if S_n dormant")
    pl.add_argument("--piston", action="store_true", help="Run piston-core per-core thermal tick")
    pl.set_defaults(func=cmd_pulse)

    lp = sub.add_parser("loop", help="1 Hz CPU automaton (RID feed + pulse artifact)")
    lp.add_argument("--interval", type=float, default=1.0)
    lp.add_argument("--json", default="", help="Pulse artifact path")
    lp.add_argument("--no-journal", action="store_true", help="Skip automation rid_logs write")
    lp.add_argument("--piston", action="store_true", help="Run piston-core per-core thermal tick each beat")
    lp.set_defaults(func=cmd_loop)

    sub.add_parser("supervisor", help="Show automation RID supervisor state").set_defaults(func=cmd_supervisor)

    ms = sub.add_parser("master", help="Show hierarchical Master S_n (all subsystems)")
    ms.add_argument("--live", action="store_true", help="Compute fresh sample now")
    ms.add_argument("--json", action="store_true")
    ms.set_defaults(func=cmd_master)

    nr = sub.add_parser("narrator", help="Render latest RID event to narrator.txt")
    nr.add_argument("--quiet", action="store_true")
    nr.add_argument("--json", action="store_true")
    nr.set_defaults(func=cmd_narrator)

    gt = sub.add_parser("gate", help="RID + quorum run authority check")
    gt.add_argument("--risk", default="low", choices=["low", "normal", "high", "destructive", "external"])
    gt.add_argument("--irreversible", action="store_true")
    gt.add_argument("--json", action="store_true")
    gt.set_defaults(func=cmd_gate)

    rn = sub.add_parser("run", help="Full CPU automaton beat or loop")
    rn.add_argument("--once", action="store_true", help="Single beat then exit")
    rn.add_argument("--interval", type=float, default=1.0)
    rn.add_argument("--json", default="", help="Pulse artifact path")
    rn.add_argument("--json-out", default="", help="Write full beat report JSON")
    rn.add_argument("--quiet", action="store_true")
    rn.add_argument("--no-journal", action="store_true")
    rn.add_argument("--no-narrator", action="store_true")
    rn.add_argument("--runtime-tick", action="store_true", help="Run agentic_runtime if gate allows")
    rn.add_argument("--max-tasks", type=int, default=1)
    rn.add_argument("--allow-denied", action="store_true", help="Exit 0 even if gate denies")
    rn.add_argument("--piston", action="store_true", help="Run piston-core per-core thermal tick each beat")
    rn.set_defaults(func=cmd_run)

    sub.add_parser("rid-status", help="Show live RID feed freshness").set_defaults(func=cmd_rid_status)
    sub.add_parser("paths", help="Print resolved automation paths").set_defaults(func=cmd_paths)

    au = sub.add_parser("autonomous", help="AIOS autonomous operator (foundation-gated)")
    au.add_argument("--session-log", default="", help="Session log JSON path (default: artifacts/auto/autonomous_session.json)")
    au.add_argument("--once", action="store_true", help="Single beat then exit")
    au.add_argument("--interval", type=float, default=1.0)
    au.add_argument("--max-beats", type=int, default=0, help="0 = run until Ctrl+C")
    au.add_argument("--json", default="", help="Pulse artifact path")
    au.add_argument("--json-out", default="", help="Write beat report JSON")
    au.add_argument("--no-journal", action="store_true")
    au.add_argument("--narrator", action="store_true", help="Print narrator line each beat")
    au.add_argument("--no-piston", action="store_true")
    au.add_argument("--runtime-tick", action="store_true", default=True)
    au.add_argument("--max-tasks", type=int, default=1)
    au.set_defaults(func=cmd_autonomous)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
