#!/usr/bin/env python3
"""Plan-only orchestrator for privacy, support, and dream service cores.

Default is ``--plan-only``. Writes receipts under
``foundation/artifacts/auto/service_cores_automation/``.

Never starts AIOS, never copies weight packs, never runs dream cycles,
never deletes archives, never stresses the plant.

Examples:

    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_service_cores_automation_v1.py --inventory
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_service_cores_automation_v1.py --core all --plan-only
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_service_cores_automation_v1.py --core privacy --plan-only
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_service_cores_automation_v1.py --core support --plan-only
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_service_cores_automation_v1.py --core dream --plan-only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.service_cores_automation import (  # noqa: E402
    RECEIPTS_ROOT,
    SERVICE_CORE_IDS,
    get_spec,
    inventory,
    list_specs,
    run_all_plans,
    run_closed_smoke,
    run_plan,
    write_receipt,
    _utc_stamp,
)


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the three service-core specs and exit.",
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Print inventory (adapters/cores/tests/docs presence) and exit.",
    )
    parser.add_argument(
        "--core",
        choices=(*SERVICE_CORE_IDS, "all"),
        default="all",
        help="Which service core to plan (default: all).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--plan-only",
        action="store_true",
        help="Plan-only (default when neither flag is passed).",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Run bounded closed_smoke when the core allows it (privacy/support).",
    )
    args = parser.parse_args()
    plan_only = not args.execute  # default plan-only

    if args.list:
        _print(
            {
                "ok": True,
                "receipts_root": str(RECEIPTS_ROOT).replace("\\", "/"),
                "cores": list(SERVICE_CORE_IDS),
                "specs": list_specs(),
                "aios_runtime_started": False,
            }
        )
        return 0

    if args.inventory:
        payload = inventory()
        _print(payload)
        return 0 if payload.get("ok") else 1

    if args.execute and args.core == "all":
        _print(
            {
                "ok": False,
                "error": "execute_requires_single_core",
                "hint": "use --core privacy|support --execute (dream remains plan-only)",
                "aios_runtime_started": False,
            }
        )
        return 2

    stamp = _utc_stamp()
    if plan_only or args.core == "all":
        if args.core == "all":
            result = run_all_plans()
            receipt_stamp = f"{stamp}_all"
        else:
            result = run_plan(args.core)
            receipt_stamp = f"{stamp}_{args.core}"
    else:
        # --execute path for a single core
        if get_spec(args.core) is None:
            _print({"ok": False, "error": "unknown_core", "core": args.core})
            return 2
        result = run_closed_smoke(args.core)
        receipt_stamp = f"{stamp}_{args.core}_execute"

    receipt_path = write_receipt(result, stamp=receipt_stamp)
    summary = {
        "ok": bool(result.get("ok")),
        "receipt": str(receipt_path).replace("\\", "/"),
        "receipt_md": str(receipt_path.with_name("RECEIPT.md")).replace("\\", "/"),
        "stamp": receipt_stamp,
        "core": args.core,
        "mode": result.get("mode") or "plan_only",
        "receipts_root": str(RECEIPTS_ROOT).replace("\\", "/"),
        "aios_runtime_started": False,
        "deny_weight_packs": True,
        "error": result.get("error"),
    }
    if isinstance(result.get("results"), dict):
        summary["per_core_ok"] = {
            key: bool(row.get("ok")) for key, row in result["results"].items()
        }
    _print(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
