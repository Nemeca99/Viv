#!/usr/bin/env python3
"""
AIOS sovereign entry — boot / run / status / halt.

One command surface for the whole organism (RID + agentic + CPU teach + UML + voice).
Pillar CLIs (rid_main / auto_main / uml_main) remain for deep ops; this is the living system.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_VIV = _ROOT.parent
for _p in (_ROOT, _VIV):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.aios_organism import (  # noqa: E402
    boot,
    clear_halt,
    halt,
    organism_beat,
    organism_run,
    seed_curriculum,
    status,
)
from lib.aios_inbox import (  # noqa: E402
    INBOX_PATH,
    OUTBOX_PATH,
    TASK_BOARD_MD,
    publish_task_board,
    submit,
)

VERSION = "1.1.0"


def cmd_boot(args: argparse.Namespace) -> int:
    report = boot(seed=not args.no_seed, clear_halt=args.clear_halt)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


def cmd_run(args: argparse.Namespace) -> int:
    """Living loop = PRT autonomous (Architect design), NOT absorb theater."""
    from lib.prt_overnight import clear_overnight_halt, run_autonomous

    boot_rep = boot(seed=True)
    if not boot_rep.get("ok"):
        print(json.dumps(boot_rep, indent=2, default=str))
        return 2

    sn = ((boot_rep.get("pillars") or {}).get("rid") or {}).get("master_s_n")
    print(f"[AIOS] boot ok  S_n={sn}")
    print("[AIOS] Living loop = PRT autonomous (collect->apply->integrity->cooldown).")
    print("[AIOS] NOT the absorb checklist. Absorb is: aios_main.py absorb / systems")
    print("[AIOS] voice_speak follows cpu_config.autonomy.voice_speak")
    print("[AIOS] Halt: prt_main.py autonomous halt   OR   Ctrl+C")
    print(
        "[AIOS] GPU LoRA apply requires cpu_config.prt.gpu_overnight_enabled=true "
        "(otherwise REFUSED / use --dry-run for gate-only proof)"
    )

    clear_overnight_halt()
    auto_cfg = Path(r"L:/Continue/Viv/foundation/artifacts/models/prt_autonomous_config.json")
    report = run_autonomous(
        max_hours=None,
        cooldown_s=float(args.interval) if args.interval else None,
        dry_run=bool(getattr(args, "dry_run", False)),
        capability_expansion=bool(getattr(args, "with_capability_expansion", False)),
        max_rounds=args.beats,
        config_path=auto_cfg if auto_cfg.is_file() else None,
    )
    print(json.dumps({k: v for k, v in report.items() if k != "history"}, indent=2, default=str))
    if report.get("history"):
        print(f"[AIOS] rounds_done={report.get('rounds_done')} status={report.get('status')} reason={report.get('reason')}")
    if report.get("status") == "REFUSED":
        print("[AIOS] REFUSED — enable GPU overnight or pass --dry-run for non-GPU proof.")
        return 5
    if report.get("status") == "HALTED":
        return 3
    return 0 if report.get("ok") else 1


def cmd_beat(args: argparse.Namespace) -> int:
    report = organism_beat(max_tasks=args.max_tasks, speak=args.speak, narrate=args.narrate)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


def cmd_status(_: argparse.Namespace) -> int:
    print(json.dumps(status(), indent=2, default=str))
    return 0


def cmd_halt(args: argparse.Namespace) -> int:
    print(json.dumps(halt(args.reason), indent=2))
    return 0


def cmd_resume(_: argparse.Namespace) -> int:
    print(json.dumps(clear_halt(), indent=2, default=str))
    return 0


def cmd_seed(_: argparse.Namespace) -> int:
    print(json.dumps(seed_curriculum(force=True), indent=2, default=str))
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    text = " ".join(args.text).strip()
    if not text:
        print("usage: aios_main.py ask \"your goal or request\"", file=sys.stderr)
        return 2
    from lib.master_rid import load_master_rid
    from lib.triad_kernel import (
        TriadDenied,
        TriadEnvelope,
        authorize_operation,
        emit,
        open_context,
    )

    master = load_master_rid()
    s_n = float(master.master_s_n) if master is not None else 0.50
    try:
        context = open_context(
            TriadEnvelope.build(
                actor="architect",
                source="aios_cli",
                target="organism_inbox",
                action="ASK",
                payload={
                    "text": text,
                    "action": args.action or None,
                    "priority": args.priority,
                },
                s_n=s_n,
            )
        )
        authorize_operation(
            context,
            operation="inbox.submit",
            params={
                "path": str(INBOX_PATH).replace("\\", "/"),
                "content": text,
            },
            tool_name="write_file",
        )
        row = submit(text, action=args.action or None, priority=args.priority)
        output = (
            f"MISSION QUEUED: {text}\n"
            f"  mission_id={row.get('mission_id')}\n"
            f"  steps={row.get('steps')}\n"
            "  Next run beat will execute the Security-wrapped Triad chain.\n"
            "  ACTIVITY: L:/Continue/Viv/foundation/artifacts/auto/organism/ACTIVITY.md"
        )
        filtered, _receipt = emit(context, output)
        print(filtered)
    except TriadDenied as exc:
        print(
            json.dumps(
                {"ok": False, "blocked": True, "reason": exc.reason, "evidence": exc.evidence},
                default=str,
            ),
            file=sys.stderr,
        )
        return 3
    return 0


def cmd_triad(args: argparse.Namespace) -> int:
    from lib.triad_architecture import scan_architecture
    from lib.triad_kernel import triad_status, verify_triad_ledger

    if args.action == "verify":
        report = verify_triad_ledger()
    elif args.action == "architecture":
        report = scan_architecture()
    else:
        report = triad_status()
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok", report.get("error") is None) else 1


def cmd_governor(_: argparse.Namespace) -> int:
    from lib.engineering_governor import governor_status

    report = governor_status()
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("triad_ledger", {}).get("ok") else 1


def cmd_tasks(_: argparse.Namespace) -> int:
    board = publish_task_board()
    print(TASK_BOARD_MD.read_text(encoding="utf-8") if TASK_BOARD_MD.is_file() else json.dumps(board, indent=2))
    return 0


def cmd_missions(_: argparse.Namespace) -> int:
    from lib.aios_missions import missions_board, publish_activity_md

    publish_activity_md()
    print(json.dumps(missions_board(), indent=2, default=str))
    return 0


def cmd_activity(_: argparse.Namespace) -> int:
    from lib.aios_missions import ACTIVITY_MD, publish_activity_md

    path = publish_activity_md()
    print(path.read_text(encoding="utf-8") if path.is_file() else f"missing {ACTIVITY_MD}")
    return 0


def cmd_goal(args: argparse.Namespace) -> int:
    from lib.aios_goals import add_goal, list_goals

    text = " ".join(args.text).strip()
    if not text:
        print('usage: aios_main.py goal "high-level objective"', file=sys.stderr)
        return 2
    g = add_goal(text, success=args.success or "", priority=args.priority, source="architect")
    print(f"GOAL SEEDED: {g.get('objective')}")
    print(f"  goal_id={g.get('goal_id')} priority={g.get('priority')} status={g.get('status')}")
    print(f"  board=L:/Continue/Viv/sandbox/work/goals.json")
    print(f"  active_goals={len(list_goals(status='active'))}")
    return 0


def cmd_goals(_: argparse.Namespace) -> int:
    from lib.aios_goals import GOALS_PATH, ensure_goals, list_goals

    ensure_goals()
    rows = list_goals()
    print(f"goals_path={GOALS_PATH}")
    if not rows:
        print("(empty — seed with: aios_main.py goal \"...\")")
        return 0
    for g in rows:
        print(
            f"  [{g.get('status')}] p={g.get('priority')} {g.get('goal_id')} "
            f"step={g.get('step_index')}/{len(g.get('plan') or [])} "
            f"{(g.get('objective') or '')[:100]}"
        )
    return 0


def cmd_systems(_: argparse.Namespace) -> int:
    from lib.aios_systems import write_registry

    rep = write_registry()
    print(f"registry={rep.get('registry_md')}")
    print(f"counts={rep.get('counts')}")
    nxt = rep.get("next")
    if nxt:
        print(f"NEXT: {nxt.get('generation')}/{nxt.get('id')} — {nxt.get('role')} [{nxt.get('status')}]")
    print("Absorb queue (top 8):")
    for q in (rep.get("absorb_queue") or [])[:8]:
        print(f"  p={q['priority']} {q['generation']}/{q['id']} [{q['status']}] {q['role']}")
    return 0


def cmd_absorb(args: argparse.Namespace) -> int:
    from lib.aios_absorb import absorb_knowledge, absorb_next, absorb_steel_judge, survey_and_write_registry
    from lib.master_rid import load_master_rid

    try:
        sn = float(load_master_rid().master_s_n)
    except Exception:
        sn = 0.5
    which = (args.which or "next").lower()
    if which == "survey":
        out = survey_and_write_registry()
    elif which == "steel":
        out = absorb_steel_judge(s_n=sn)
    elif which == "knowledge":
        out = absorb_knowledge(s_n=sn)
    else:
        out = absorb_next(s_n=sn)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aios_main",
        description="AIOS organism — boot/run + operator ask/tasks",
    )
    p.add_argument("--version", action="version", version=f"aios_main {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("boot", help="Foundation + security + curriculum + voice + RID online")
    b.add_argument("--no-seed", action="store_true")
    b.add_argument("--clear-halt", action="store_true")
    b.set_defaults(func=cmd_boot)

    r = sub.add_parser(
        "run",
        help="Living AIOS = PRT autonomous (collect/apply/integrity). Not absorb theater.",
    )
    r.add_argument("--interval", type=float, default=120.0, help="Cooldown between PRT rounds (cooldown_s)")
    r.add_argument("--beats", type=int, default=None, help="Stop after N PRT rounds (default: perpetual)")
    r.add_argument("--max-tasks", type=int, default=3, help="Ignored on PRT run (legacy flag)")
    r.add_argument("--speak-every", type=int, default=5, help="Ignored on PRT run — voice follows cpu_config")
    r.add_argument(
        "--dry-run",
        action="store_true",
        help="Gate/observe only — no GPU LoRA apply (proof when overnight GPU parked)",
    )
    r.add_argument(
        "--with-capability-expansion",
        action="store_true",
        help="After integrity pass, PRT-scored sandbox expansion (default OFF)",
    )
    r.set_defaults(func=cmd_run)

    bt = sub.add_parser("beat", help="One organism beat (absorb/missions) — not the living PRT loop")
    bt.add_argument("--max-tasks", type=int, default=3)
    bt.add_argument("--speak", action="store_true")
    bt.add_argument("--narrate", action="store_true")
    bt.set_defaults(func=cmd_beat)

    org = sub.add_parser(
        "organism",
        help="Legacy absorb/mission organism loop (NOT PRT — only if you explicitly want it)",
    )
    org.add_argument("--interval", type=float, default=2.0)
    org.add_argument("--beats", type=int, default=None)
    org.add_argument("--max-tasks", type=int, default=3)
    org.add_argument("--speak-every", type=int, default=5)
    org.set_defaults(func=lambda a: organism_run(
        interval_s=a.interval, max_beats=a.beats, max_tasks=a.max_tasks, speak_every=a.speak_every
    ))

    sub.add_parser("status", help="Full organism dashboard").set_defaults(func=cmd_status)
    sub.add_parser("seed", help="Force-seed cross-pillar curriculum").set_defaults(func=cmd_seed)

    ask = sub.add_parser("ask", help="Give her work (inbox) — works while run is live")
    ask.add_argument("text", nargs="+", help="Goal / request in plain English")
    ask.add_argument("--action", default="", help="Optional: uml|remember|note|speak|status|plan")
    ask.add_argument("--priority", type=int, default=20)
    ask.set_defaults(func=cmd_ask)

    g = sub.add_parser("goal", help="Seed a standing Level-3 goal (Architect once; agent owns the how)")
    g.add_argument("text", nargs="+", help="High-level objective")
    g.add_argument("--success", default="", help="Optional success criteria")
    g.add_argument("--priority", type=int, default=50)
    g.set_defaults(func=cmd_goal)

    sub.add_parser("goals", help="List standing goals board").set_defaults(func=cmd_goals)
    sub.add_parser("systems", help="Scan V1+V2 AIOS cores vs Viv — write systems registry").set_defaults(func=cmd_systems)
    ab = sub.add_parser("absorb", help="Absorb next LEGACY core (or steel|knowledge|survey)")
    ab.add_argument("which", nargs="?", default="next", help="next|survey|steel|knowledge")
    ab.set_defaults(func=cmd_absorb)
    sub.add_parser("tasks", help="Show task board (missions + queue)").set_defaults(func=cmd_tasks)
    sub.add_parser("missions", help="Show mission JSON board").set_defaults(func=cmd_missions)
    sub.add_parser("activity", help="Show ACTIVITY.md feed").set_defaults(func=cmd_activity)
    triad = sub.add_parser("triad", help="Security-wrapped RID/AUTO/UML kernel status")
    triad.add_argument("action", choices=["status", "verify", "architecture"], default="status", nargs="?")
    triad.set_defaults(func=cmd_triad)
    sub.add_parser("governor", help="Engineering Governor transaction status").set_defaults(func=cmd_governor)

    h = sub.add_parser("halt", help="Write halt.flag — organism stops")
    h.add_argument("--reason", default="operator_halt")
    h.set_defaults(func=cmd_halt)

    sub.add_parser("resume", help="Clear halt + agentic resume").set_defaults(func=cmd_resume)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
