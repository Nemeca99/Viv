#!/usr/bin/env python3
"""Viv foundation — Guardian v2 CPU gate (Intellexi + intent)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.guardian_v2 import evaluate_guardian
from lib.rid_feed import read_live

VERSION = "1.0.0"


def _live_s_n() -> float:
    live = read_live(max_age_s=10.0)
    return live.s_n if live else 1.0


def cmd_eval(args: argparse.Namespace) -> int:
    text = " ".join(args.text)
    s_n = args.s_n if args.s_n is not None else _live_s_n()
    verdict = evaluate_guardian(text, s_n=s_n)
    if args.json:
        print(json.dumps(verdict.to_dict(), indent=2))
    else:
        print(verdict.message)
        print(
            f"allowed={verdict.allowed} stage={verdict.stage} S_n={verdict.s_n:.4f} "
            f"LTP={verdict.ltp:.4f} demand={verdict.demand_d_n:.2f}"
        )
        if verdict.sanctuary_triggered:
            print(f"sanctuary: {verdict.sanctuary_reason}")
        if verdict.flagged_tokens:
            print(f"tariff tokens: {', '.join(verdict.flagged_tokens)}")
    return 0 if verdict.allowed else 2


def cmd_demo(_: argparse.Namespace) -> int:
    cases = [
        ("read_file logs.txt", 0.8),
        ("eval exec delete everything", 0.8),
        ("[3,4]", 0.8),
        ("temp_gpio read", 0.3),
    ]
    for text, sn in cases:
        v = evaluate_guardian(text, s_n=sn)
        mark = "ALLOW" if v.allowed else "BLOCK"
        print(f"[{mark}] {text!r} -> {v.stage}: {v.message}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="guardian_main", description="Guardian v2 CPU gate")
    p.add_argument("--version", action="version", version=f"guardian_main {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    ev = sub.add_parser("eval", help="Evaluate text through Guardian v2")
    ev.add_argument("text", nargs="+")
    ev.add_argument("--s-n", type=float, default=None)
    ev.add_argument("--json", action="store_true")
    ev.set_defaults(func=cmd_eval)

    sub.add_parser("demo", help="Run built-in allow/block examples").set_defaults(func=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
