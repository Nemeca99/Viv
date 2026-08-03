#!/usr/bin/env python3
"""Viv agentic operator CLI — queue / tick / resume (Rust-gated)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.agentic_runtime import (  # noqa: E402
    enqueue,
    needs_resume,
    resume,
    run_once,
    status,
)

VERSION = "0.1.0"


def cmd_status(_: argparse.Namespace) -> int:
    print(json.dumps(status(), indent=2, default=str))
    return 0


def cmd_tick(args: argparse.Namespace) -> int:
    report = run_once(max_tasks=args.max_tasks)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") and report.get("exit_code", 0) == 0 else 1


def cmd_resume(_: argparse.Namespace) -> int:
    print(json.dumps(resume(), indent=2, default=str))
    return 0


def cmd_enqueue(args: argparse.Namespace) -> int:
    payload: dict = {}
    if args.params:
        payload = json.loads(args.params)
    if args.path:
        payload["path"] = args.path
    if args.content is not None:
        payload["content"] = args.content
    if args.line:
        payload["line"] = args.line
    task = enqueue(
        kind=args.kind,
        title=args.title or args.kind,
        payload=payload,
        priority=args.priority,
    )
    print(json.dumps(task.to_dict(), indent=2))
    return 0


def cmd_seed(_: argparse.Namespace) -> int:
    """Seed a safe health_check + sandbox note for overnight proof."""
    a = enqueue(kind="health_check", title="Security membrane health", priority=10)
    b = enqueue(
        kind="write_note",
        title="Sandbox heartbeat note",
        priority=20,
        payload={
            "path": "L:/Continue/Viv/sandbox/agentic_seed.txt",
            "content": "Viv agentic seed — security-gated write.\n",
        },
    )
    print(json.dumps({"seeded": [a.task_id, b.task_id]}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentic_main", description="Viv agentic queue (Rust-gated)")
    p.add_argument("--version", action="version", version=f"agentic_main {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Queue + security status").set_defaults(func=cmd_status)

    tick = sub.add_parser("tick", help="Process ready tasks")
    tick.add_argument("--max-tasks", type=int, default=1)
    tick.set_defaults(func=cmd_tick)

    sub.add_parser("resume", help="Clear requires_operator_resume").set_defaults(func=cmd_resume)
    sub.add_parser("seed", help="Enqueue safe health + sandbox write").set_defaults(func=cmd_seed)

    en = sub.add_parser("enqueue", help="Add a task")
    en.add_argument(
        "kind",
        choices=[
            "noop",
            "health_check",
            "write_note",
            "append_journal",
            "memory_append",
            "memory_retrieve",
            "cpu_rid_observe",
            "uml_eval",
            "rid_sample",
            "guardian_pulse",
            "voice_status",
            "speak_brief",
            "plant_brief",
            "operator_goal",
            "uml_workbook",
        ],
    )
    en.add_argument("--title", default="")
    en.add_argument("--params", default="", help="JSON payload")
    en.add_argument("--path", default="")
    en.add_argument("--content", default=None)
    en.add_argument("--line", default="")
    en.add_argument("--priority", type=int, default=100)
    en.set_defaults(func=cmd_enqueue)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if needs_resume() and args.command not in ("resume", "status"):
        print(json.dumps({"warning": "runtime requires resume", "hint": "agentic_main.py resume"}))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
