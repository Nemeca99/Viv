#!/usr/bin/env python3
"""Bounded RID / plant foundation automation (plan-first).

RID-first control plane for foundation health and plant surfaces. Default is
``--plan-only``. Profile ``health_quick`` runs short non-stress checks under
60s when executed; otherwise emits a clear SKIP stub.

NEVER auto-runs 120s stress captures. ``--i-understand-long-plant`` only
documents the operator command in the receipt.

Does not start/stop AIOS.

Examples:

    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_rid_plant_automation_v1.py
    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_rid_plant_automation_v1.py --plan-only
    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_rid_plant_automation_v1.py --profile health_quick --execute
    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_rid_plant_automation_v1.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.rid_plant_automation_v1 import (  # noqa: E402
    PROFILE_HEALTH_QUICK,
    RECEIPTS_ROOT,
    build_execute_receipt,
    build_plan_receipt,
    list_profiles,
    write_receipt,
    _utc_stamp,
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
    parser.add_argument(
        "--list",
        action="store_true",
        help="List profiles and exit.",
    )
    parser.add_argument(
        "--profile",
        choices=(PROFILE_HEALTH_QUICK,),
        default=PROFILE_HEALTH_QUICK,
        help="Automation profile (default: health_quick).",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        default=True,
        help="Plan/document only (default). No health execute, no 120s plant.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run health_quick non-stress checks (<60s). Overrides plan-only.",
    )
    parser.add_argument(
        "--i-understand-long-plant",
        action="store_true",
        help=(
            "Acknowledge 120s stressed plant proof. Documents the rid_main "
            "stability command in the receipt; does NOT auto-run it."
        ),
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run embedded selftest and exit.",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        import runpy

        test_path = Path(__file__).resolve().parent / "test_rid_plant_automation_v1.py"
        ns = runpy.run_path(str(test_path), run_name="__rid_plant_selftest__")
        selftest_main = ns.get("main")
        if not callable(selftest_main):
            _print({"ok": False, "error": "selftest_main_missing", "path": str(test_path)})
            return 2
        return int(selftest_main())

    if args.list:
        payload = {
            "ok": True,
            "receipts_root": str(RECEIPTS_ROOT).replace("\\", "/"),
            "profiles": list_profiles(),
            "default_mode": "plan_only",
            "aios_runtime_started": False,
            "long_plant_auto": False,
        }
        _print(payload)
        return 0

    if args.execute and args.profile != PROFILE_HEALTH_QUICK:
        _print({"ok": False, "error": "unknown_execute_profile", "profile": args.profile})
        return 2

    stamp = _utc_stamp()
    plan_only = not bool(args.execute)

    if plan_only:
        receipt = build_plan_receipt(
            i_understand_long_plant=bool(args.i_understand_long_plant),
            stamp=stamp,
        )
    else:
        receipt = build_execute_receipt(
            i_understand_long_plant=bool(args.i_understand_long_plant),
            stamp=stamp,
        )

    path = write_receipt(receipt, stamp=stamp)
    summary = {
        "ok": bool(receipt.get("ok")),
        "mode": receipt.get("mode"),
        "profile": receipt.get("profile"),
        "receipt": str(path).replace("\\", "/"),
        "stamp": stamp,
        "aios_runtime_started": False,
        "long_plant_started": False,
        "long_plant_status": (receipt.get("long_plant") or {}).get("status"),
        "include_stress": receipt.get("include_stress"),
        "elapsed_s": receipt.get("elapsed_s"),
        "failed": receipt.get("failed"),
        "skipped_count": len(receipt.get("skipped") or []),
    }
    _print(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
