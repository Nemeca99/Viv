#!/usr/bin/env python3
"""Viv CARMA operator CLI — plain-text memory (past in files)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_VIV = Path(__file__).resolve().parents[1]
if str(_VIV) not in sys.path:
    sys.path.insert(0, str(_VIV))

from memory_core.semantic_memory import SemanticMemory, append_live_note, remember, retrieve, status  # noqa: E402
from memory_core.tags import define_tag, list_tags  # noqa: E402

VERSION = "0.1.0"


def cmd_status(_: argparse.Namespace) -> int:
    print(json.dumps(status(), indent=2, default=str))
    return 0


def cmd_remember(args: argparse.Namespace) -> int:
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
    out = remember(args.text, provenance=args.provenance, tags=tags)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


def cmd_retrieve(args: argparse.Namespace) -> int:
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
    hits = retrieve(args.query, top=args.top, tags=tags)
    print(json.dumps({"query": args.query, "hits": hits}, indent=2, default=str))
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    if args.action == "list":
        print(json.dumps(list_tags(), indent=2))
        return 0
    row = define_tag(args.name, args.desc or "")
    print(json.dumps(row, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memory_main", description="Viv plain-text CARMA")
    p.add_argument("--version", action="version", version=f"memory_main {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="CARMA layout + counts").set_defaults(func=cmd_status)

    rm = sub.add_parser("remember", help="Append a memory line")
    rm.add_argument("text")
    rm.add_argument("--provenance", default="live", choices=["live", "dream", "simulation"])
    rm.add_argument("--tags", default="", help="Comma-separated tags")
    rm.set_defaults(func=cmd_remember)

    rt = sub.add_parser("retrieve", help="Keyword retrieve")
    rt.add_argument("query")
    rt.add_argument("--top", type=int, default=5)
    rt.add_argument("--tags", default="")
    rt.set_defaults(func=cmd_retrieve)

    tg = sub.add_parser("tags", help="Master tag file")
    tg.add_argument("action", choices=["list", "define"])
    tg.add_argument("name", nargs="?", default="")
    tg.add_argument("--desc", default="")
    tg.set_defaults(func=cmd_tags)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
