#!/usr/bin/env python3
"""Plan-only automation for CARMA + consciousness cores (backup_core pattern).

Default mode is ``--plan-only``: run fixture ``cpu_plan`` surfaces and write a
receipt under ``foundation/artifacts/auto/cognitive_cores_automation/``.

Never starts AIOS, never calls live ``remember()``, never durable-commits LTM,
never executes V2 biological loops.

Examples:

    L:\\Continue\\.venv\\Scripts\\python.exe foundation\\scripts\\run_cognitive_cores_automation_v1.py --profile carma --plan-only
    L:\\Continue\\.venv\\Scripts\\python.exe foundation\\scripts\\run_cognitive_cores_automation_v1.py --profile consciousness --plan-only
    L:\\Continue\\.venv\\Scripts\\python.exe foundation\\scripts\\run_cognitive_cores_automation_v1.py --profile both --plan-only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cognitive_cores_automation_v1 import (  # noqa: E402
    EXECUTE_MEANING,
    PROFILES,
    list_profiles,
    plan_profile,
    refuse_execute,
    write_receipt,
    _utc_stamp,
)


def _print(payload: dict) -> None:
    # Windows consoles are often cp1252; keep stdout ASCII-safe JSON.
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
        choices=PROFILES,
        default=None,
        help="carma | consciousness | both",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Run fixture cpu_plan only (default when --profile is set).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Refused: documents why execute is not allowed for these cores.",
    )
    parser.add_argument(
        "--explicit-commit",
        action="store_true",
        help="Record commit-intent handoff in the plan (still no durable write).",
    )
    args = parser.parse_args(argv)

    if args.list or args.profile is None:
        if args.profile is None and not args.list:
            parser.print_help()
            print("\n# profiles")
            for row in list_profiles():
                print(
                    f"  {row['profile_id']:14} core={row['core_id']:20} "
                    f"default={row['default_mode']} execute={row['execute_allowed']}"
                )
            return 0
        _print({"ok": True, "profiles": list_profiles(), "aios_runtime_started": False})
        return 0

    if args.execute and args.plan_only:
        _print({"ok": False, "error": "conflicting_flags", "detail": "use either --plan-only or --execute"})
        return 2

    stamp = _utc_stamp()
    profile = args.profile

    if args.execute:
        result = refuse_execute(profile)
        path = write_receipt(result, stamp=f"{stamp}_{profile}_execute_refused")
        _print(
            {
                "ok": False,
                "receipt": str(path).replace("\\", "/"),
                "profile": profile,
                "mode": "execute_refused",
                "error": result.get("error"),
                "execute_meaning": result.get("execute_meaning") or EXECUTE_MEANING.get(profile),
                "aios_runtime_started": False,
            }
        )
        return 3

    # Default: plan-only when profile is set (even without the flag).
    result = plan_profile(profile, explicit_commit=bool(args.explicit_commit))
    result["mode"] = "plan_only"
    path = write_receipt(result, stamp=f"{stamp}_{profile}")
    summary = {
        "ok": bool(result.get("ok")),
        "receipt": str(path).replace("\\", "/"),
        "stamp": f"{stamp}_{profile}",
        "profile": profile,
        "core_id": result.get("core_id"),
        "mode": "plan_only",
        "writes_performed": False,
        "durable_commit_performed": False,
        "aios_runtime_started": False,
        "execution_approved": False,
        "llm_authority": False,
    }
    if profile == "both":
        summary["carma_ok"] = bool((result.get("carma") or {}).get("ok"))
        summary["consciousness_ok"] = bool((result.get("consciousness") or {}).get("ok"))
    elif profile == "carma":
        plan = result.get("plan") or {}
        summary["retrieval_state"] = (plan.get("retrieval") or {}).get("state")
        summary["stm_ltm_state"] = (plan.get("stm_ltm") or {}).get("state")
    elif profile == "consciousness":
        plan = result.get("plan") or {}
        summary["commit_state"] = (plan.get("cycle") or {}).get("memory_commit", {}).get("state")
        summary["fragment"] = (plan.get("fragment") or {}).get("selected")
    _print(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
