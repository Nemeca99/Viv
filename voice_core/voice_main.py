#!/usr/bin/env python3
"""Viv voice_core operator CLI — status | speak | stub | packet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_VIV = Path(__file__).resolve().parents[1]
_FOUNDATION = _VIV / "foundation"
for _p in (_VIV, _FOUNDATION):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from voice_core.client import voice_endpoint  # noqa: E402
from voice_core.intent_packet import build_intent_packet  # noqa: E402
from voice_core.speak import speak, speak_status  # noqa: E402
from voice_core.stub_server import main as stub_main  # noqa: E402

VERSION = "0.1.0"


def cmd_status(_: argparse.Namespace) -> int:
    st = speak_status()
    print(json.dumps(st, indent=2, default=str))
    # Soft-fail silent OK when offline
    return 0


def cmd_speak(args: argparse.Namespace) -> int:
    out = speak(
        args.text,
        memory_top=args.top,
        max_tokens=args.max_tokens,
        knowledge_query=args.knowledge_query,
        knowledge_mode=args.knowledge_mode,
        wikipedia_title=args.wikipedia_title,
        include_legacy_wikipedia=args.legacy_wikipedia,
        resolve_legacy_redirects=args.resolve_redirects,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


def cmd_packet(args: argparse.Namespace) -> int:
    packet = build_intent_packet(query=args.query, memory_top=args.top)
    if args.json:
        print(json.dumps(packet, indent=2, default=str))
    else:
        print(f"s_n={packet['s_n']} status={packet['status']} tone={packet['tone']}")
        print(f"facts ({len(packet['facts'])}):")
        for f in packet["facts"]:
            print(f"  - {f}")
        print(f"memory ({len(packet['memory'])}):")
        for m in packet["memory"]:
            print(f"  - [{m.get('score')}] {(m.get('text') or '')[:120]}")
    return 0


def cmd_stub(args: argparse.Namespace) -> int:
    return stub_main(["--host", args.host, "--port", str(args.port)])


def cmd_endpoint(_: argparse.Namespace) -> int:
    print(json.dumps(voice_endpoint(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="voice_main", description="Viv GPU voice (optional translator)")
    p.add_argument("--version", action="version", version=f"voice_main {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Online/offline; silent OK when no server").set_defaults(func=cmd_status)

    sp = sub.add_parser("speak", help="Packet → render → Security OUT")
    sp.add_argument("text", nargs="?", default="state summary")
    sp.add_argument("--top", type=int, default=3, help="CARMA memory top-k")
    sp.add_argument("--max-tokens", type=int, default=64)
    sp.add_argument("--knowledge-query", default=None, help="CPU knowledge query to include in the mouth packet")
    sp.add_argument("--knowledge-mode", choices=("local", "multi_source"), default="local")
    sp.add_argument("--wikipedia-title", default=None, help="Explicit Wikipedia REST title for multi-source mode")
    sp.add_argument("--legacy-wikipedia", action="store_true", help="Include the local Wikipedia corpus through the read-only adapter")
    sp.add_argument("--resolve-redirects", action="store_true", help="Resolve local Wikipedia redirects through verified corpus provenance")
    sp.set_defaults(func=cmd_speak)

    pk = sub.add_parser("packet", help="Show CPU intent packet (CARMA + S_n)")
    pk.add_argument("query", nargs="?", default="state summary")
    pk.add_argument("--json", action="store_true")
    pk.add_argument("--top", type=int, default=3)
    pk.set_defaults(func=cmd_packet)

    st = sub.add_parser("stub", help="Run local stub server (no GPU / no weights)")
    st.add_argument("--host", default="127.0.0.1")
    st.add_argument("--port", type=int, default=8000)
    st.set_defaults(func=cmd_stub)

    sub.add_parser("endpoint", help="Show configured voice URL").set_defaults(func=cmd_endpoint)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
