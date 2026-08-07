#!/usr/bin/env python3
"""AIOS skeleton subagent worker bus CLI (v1).

Local subprocess jobs with receipts. Not Cursor Task fanout.

Examples:

    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_subagent_v1.py --list
    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_subagent_v1.py --run selftest_ping
    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_subagent_v1.py --run preflight --plan-only --timeout-s 60
    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_subagent_v1.py --fanout selftest_ping,vision --timeout-s 30
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_subagent_v1 import (  # noqa: E402
    COMPUTE_CORE_HOOK,
    DEFAULT_FANOUT_CONCURRENCY,
    MAX_FANOUT_CONCURRENCY,
    RECEIPTS_ROOT,
    SCHEMA_VERSION,
    VERSION,
    fanout_subagents,
    list_profiles,
    run_subagent,
)


def _print(payload: dict) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=True, default=str)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true", help="List registered subagent profiles.")
    parser.add_argument(
        "--run",
        metavar="PROFILE",
        default=None,
        help="Run one named profile (fail-closed if unknown).",
    )
    parser.add_argument(
        "--fanout",
        metavar="PROFILES",
        default=None,
        help="Comma-separated profiles; bounded parallel (cap %d)." % MAX_FANOUT_CONCURRENCY,
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_FANOUT_CONCURRENCY,
        help="Fanout concurrency (max %d)." % MAX_FANOUT_CONCURRENCY,
    )
    parser.add_argument("--timeout-s", type=float, default=None, help="Per-job timeout seconds.")
    parser.add_argument("--max-steps", type=int, default=None, help="Budget max steps (skeleton=1).")
    parser.add_argument("--objective-id", default=None, help="Objective id for receipt.")
    parser.add_argument(
        "--parent-turn",
        default=None,
        help="Parent turn/token id (CPU single-turn authority).",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        default=True,
        help="Plan-only / stub path (default). Destructive/unknown stay plan-only.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Request execute when profile allows (skeleton: almost never).",
    )
    parser.add_argument(
        "--enable-aios-start",
        action="store_true",
        help="Refused in v1 (recorded as REFUSED).",
    )
    parser.add_argument(
        "--enable-soft-099",
        action="store_true",
        help="Refused in v1 (recorded as REFUSED).",
    )
    parser.add_argument(
        "--enable-bridge-canary",
        action="store_true",
        help="Refused in v1 (canary stays default OFF).",
    )
    args = parser.parse_args(argv)

    if args.list and not args.run and not args.fanout:
        payload = {
            "ok": True,
            "schema_version": SCHEMA_VERSION,
            "module": "aios_subagent",
            "version": VERSION,
            "receipts_root": str(RECEIPTS_ROOT).replace("\\", "/"),
            "fanout_cap": MAX_FANOUT_CONCURRENCY,
            "compute_core_hook": COMPUTE_CORE_HOOK,
            "profiles": list_profiles(),
            "aios_runtime_started": False,
            "soft_0_99": False,
            "bridge_canary_enabled": False,
        }
        _print(payload)
        return 0

    if args.fanout:
        ids = [p.strip() for p in str(args.fanout).split(",") if p.strip()]
        result = fanout_subagents(
            ids,
            concurrency=args.concurrency,
            objective_id=args.objective_id,
            parent_turn_token_id=args.parent_turn,
            timeout_s=args.timeout_s,
            plan_only=not args.execute,
        )
        _print(result)
        return 0 if result.get("ok") else 1

    if args.run:
        result = run_subagent(
            args.run,
            objective_id=args.objective_id,
            parent_turn_token_id=args.parent_turn,
            timeout_s=args.timeout_s,
            max_steps=args.max_steps,
            plan_only=not args.execute,
            execute=bool(args.execute),
            enable_aios_start=bool(args.enable_aios_start),
            enable_soft_099=bool(args.enable_soft_099),
            enable_bridge_canary=bool(args.enable_bridge_canary),
        )
        _print(result)
        if result.get("outcome") == "FAIL_CLOSED":
            return 2
        return 0 if result.get("ok") else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
