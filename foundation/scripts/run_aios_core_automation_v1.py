#!/usr/bin/env python3
"""Unified local AIOS core automation surface (plan-first).

Integrates sibling runners without duplicating them:

- systems preflight (``run_aios_systems_preflight_v1.py`` / plan-only catalog)
- training automation (``run_training_automation_v1.py`` catalog / ``uml_status``)
- backup (``run_backup_core_automation_v1.py --profile uml_lane``)

Profiles are tagged to ``COLD_START.md`` Phases 0–8. This is not a parallel
roadmap.

Never starts the AIOS runtime, never launches GPU_LONG, never activates
federation against real endpoints, never promotes bridges, never copies
weight packs / GPU trees.

Examples:

    # Default integrated plan-only (preflight + training catalog + backup plan):
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_aios_core_automation_v1.py --plan-only

    # Safe execute (preflight + uml_status + backup uml_lane):
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_aios_core_automation_v1.py --execute-safe

    # Per-core plan / closed-smoke (secondary):
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_aios_core_automation_v1.py --list
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_aios_core_automation_v1.py --profile fractal --plan-only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_core_automation import (  # noqa: E402
    RECEIPTS_ROOT,
    ROADMAP_REFS,
    get_profile,
    inventory_rows,
    list_profiles,
    phase_map,
    run_bundle_execute_safe,
    run_bundle_plan_only,
    run_closed_smoke,
    run_plan,
    write_receipt,
    _delegate_backup,
    _utc_stamp,
)


def _print(payload: dict) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=True, default=str)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List per-core profiles / inventory / COLD_START phase map, then exit.",
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Print core inventory table (JSON) and exit.",
    )
    parser.add_argument(
        "--phase-map",
        action="store_true",
        help="Print COLD_START phase mapping for profiles + bundles, then exit.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Optional single-core profile id (secondary to integrated bundle).",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Integrated plan-only bundle (default when no --profile / --execute-safe).",
    )
    parser.add_argument(
        "--execute-safe",
        action="store_true",
        help="Integrated safe execute: preflight + uml_status + backup uml_lane.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="With --profile: run closed-smoke / backup execute when allowed.",
    )
    parser.add_argument(
        "--preflight-profile",
        choices=("quick", "full"),
        default="quick",
        help="Systems preflight profile (default: quick).",
    )
    args = parser.parse_args()

    if args.list or args.inventory or args.phase_map:
        payload = {
            "ok": True,
            "receipts_root": str(RECEIPTS_ROOT).replace("\\", "/"),
            "roadmap_refs": ROADMAP_REFS,
            "profiles": list_profiles(),
            "inventory": inventory_rows(),
            "phase_map": phase_map(),
            "aios_runtime_started": False,
            "gpu_long_launched": False,
        }
        _print(payload)
        return 0

    if args.execute_safe and (args.plan_only or args.execute or args.profile):
        _print(
            {
                "ok": False,
                "error": "conflicting_flags",
                "detail": "--execute-safe is exclusive of --plan-only/--execute/--profile",
            }
        )
        return 2

    # Primary: integrated bundle (default = plan-only).
    if args.profile is None:
        if args.execute:
            _print(
                {
                    "ok": False,
                    "error": "execute_requires_profile_or_execute_safe",
                    "hint": "use --execute-safe, or --profile <id> --execute",
                }
            )
            return 2
        stamp = _utc_stamp()
        if args.execute_safe:
            result = run_bundle_execute_safe(preflight_profile=args.preflight_profile)
            stamp_name = f"{stamp}_execute_safe"
        else:
            # Default and explicit --plan-only both run the integrated plan bundle.
            result = run_bundle_plan_only(preflight_profile=args.preflight_profile)
            stamp_name = f"{stamp}_plan_only"
        receipt_path = write_receipt(result, stamp=stamp_name)
        summary = {
            "ok": bool(result.get("ok")),
            "receipt": str(receipt_path).replace("\\", "/"),
            "stamp": stamp_name,
            "mode": result.get("mode"),
            "bundle": result.get("bundle"),
            "phase_map": result.get("phase_map"),
            "siblings": {
                name: {
                    "ok": (block or {}).get("ok"),
                    "receipt": (block or {}).get("receipt") or (block or {}).get("backup_receipt"),
                    "cold_start_phase": (block or {}).get("cold_start_phase"),
                }
                for name, block in (result.get("siblings") or {}).items()
            },
            "aios_runtime_started": False,
            "gpu_long_launched": False,
            "deny_weight_packs": True,
        }
        _print(summary)
        return 0 if summary["ok"] else 1

    # Secondary: single-core profile path.
    profile = get_profile(args.profile)
    if profile is None:
        _print(
            {
                "ok": False,
                "error": "unknown_profile",
                "profile": args.profile,
                "available": [p["profile_id"] for p in list_profiles()],
            }
        )
        return 2

    if args.execute and args.plan_only:
        _print({"ok": False, "error": "conflicting_flags", "detail": "use either --plan-only or --execute"})
        return 2

    if profile.execute_kind == "backup_delegate":
        plan_only = True if args.plan_only or not args.execute else False
        if not args.plan_only and not args.execute:
            plan_only = True  # per-core default is plan-only unless --execute
        result = _delegate_backup(
            plan_only=plan_only,
            backup_profile="uml_lane" if profile.profile_id.endswith("uml_lane") else "safe",
        )
        result["profile"] = profile.profile_id
        result["core_id"] = profile.core_id
    elif args.execute:
        if not profile.execute_allowed:
            result = {
                "ok": False,
                "error": "execute_not_allowed",
                "profile": profile.profile_id,
                "core_id": profile.core_id,
                "cold_start_phase": profile.cold_start_phase,
                "constraints": list(profile.constraints),
                "hint": "pass --plan-only or obtain operator authority for this core",
                "aios_runtime_started": False,
                "gpu_long_launched": False,
            }
        else:
            result = run_closed_smoke(profile)
    else:
        result = run_plan(profile.profile_id)

    stamp = _utc_stamp()
    receipt_path = write_receipt(result, stamp=f"{stamp}_{profile.profile_id}")
    summary = {
        "ok": bool(result.get("ok")),
        "receipt": str(receipt_path).replace("\\", "/"),
        "stamp": f"{stamp}_{profile.profile_id}",
        "profile": result.get("profile") or profile.profile_id,
        "core_id": result.get("core_id") or profile.core_id,
        "mode": result.get("mode"),
        "cold_start_phase": result.get("cold_start_phase", profile.cold_start_phase),
        "aios_runtime_started": False,
        "gpu_long_launched": False,
        "deny_weight_packs": True,
        "error": result.get("error"),
        "backup_receipt": result.get("backup_receipt"),
    }
    _print(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
