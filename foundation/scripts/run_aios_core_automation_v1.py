#!/usr/bin/env python3
"""Unified local AIOS core automation surface (plan-first).

Lists effect-closed core automation profiles and runs them with receipts.
Non-backup cores default to ``--plan-only``. Backup profiles delegate to the
existing ``run_backup_core_automation_v1.py`` runner.

Never starts the AIOS runtime, never activates federation against real
endpoints, never promotes bridges, never copies weight packs / GPU trees.

Examples:

    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_aios_core_automation_v1.py --list
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_aios_core_automation_v1.py --profile backup_uml_lane --plan-only
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_aios_core_automation_v1.py --profile infra --plan-only
    L:\\Continue\\.venv\\Scripts\\python.exe scripts\\run_aios_core_automation_v1.py --profile fractal --execute
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_core_automation import (  # noqa: E402
    RECEIPTS_ROOT,
    get_profile,
    inventory_rows,
    list_profiles,
    run_closed_smoke,
    run_plan,
    write_receipt,
    _utc_stamp,
)

PYTHON = Path(r"L:\Continue\.venv\Scripts\python.exe")
BACKUP_RUNNER = FOUNDATION / "scripts" / "run_backup_core_automation_v1.py"


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _delegate_backup(profile_id: str, *, plan_only: bool) -> dict:
    backup_profile = "uml_lane" if profile_id.endswith("uml_lane") else "safe"
    cmd = [
        str(PYTHON if PYTHON.is_file() else sys.executable),
        str(BACKUP_RUNNER),
        "--profile",
        backup_profile,
    ]
    if plan_only:
        cmd.append("--plan-only")
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(FOUNDATION), check=False)
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parsed: dict = {}
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = {"raw_stdout": stdout}
    ok = proc.returncode == 0 and bool(parsed.get("ok", False))
    return {
        "ok": ok,
        "mode": "plan_only" if plan_only else "execute",
        "profile": profile_id,
        "core_id": "backup_core",
        "backup_profile": backup_profile,
        "delegate": {
            "command": cmd,
            "returncode": proc.returncode,
            "stdout": parsed,
            "stderr": stderr[-2000:] if stderr else "",
        },
        "backup_receipt": parsed.get("receipt"),
        "aios_runtime_started": False,
        "deny_weight_packs": True,
        "federation_activation": False,
        "bridge_promotion": False,
        "soft_0_99": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List automation profiles and inventory rows, then exit.",
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Print core inventory table (JSON) and exit.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Automation profile id (see --list).",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Force plan-only (default for non-backup cores).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run bounded execute path when the profile allows it.",
    )
    args = parser.parse_args()

    if args.list or args.inventory or args.profile is None:
        if args.profile is None and not args.list and not args.inventory:
            parser.print_help()
            print("\n# profiles")
            for row in list_profiles():
                print(
                    f"  {row['profile_id']:18} core={row['core_id']:18} "
                    f"default={row['default_mode']:10} execute={row['execute_allowed']}"
                )
            return 0
        payload = {
            "ok": True,
            "receipts_root": str(RECEIPTS_ROOT).replace("\\", "/"),
            "profiles": list_profiles(),
            "inventory": inventory_rows(),
            "aios_runtime_started": False,
        }
        _print(payload)
        return 0

    profile = get_profile(args.profile)
    if profile is None:
        _print({"ok": False, "error": "unknown_profile", "profile": args.profile, "available": [p["profile_id"] for p in list_profiles()]})
        return 2

    if args.execute and args.plan_only:
        _print({"ok": False, "error": "conflicting_flags", "detail": "use either --plan-only or --execute"})
        return 2

    # Default: plan-only for non-backup; backup keeps its runner default (execute) unless --plan-only.
    if profile.execute_kind == "backup_delegate":
        plan_only = bool(args.plan_only) and not args.execute
        if args.execute:
            plan_only = False
        elif not args.plan_only and not args.execute:
            # Explicit: backup without flags still executes via delegate (matches backup runner).
            plan_only = False
        result = _delegate_backup(profile.profile_id, plan_only=plan_only)
    else:
        # Non-backup: plan-only unless --execute and profile allows.
        if args.execute:
            if not profile.execute_allowed:
                result = {
                    "ok": False,
                    "error": "execute_not_allowed",
                    "profile": profile.profile_id,
                    "core_id": profile.core_id,
                    "constraints": list(profile.constraints),
                    "hint": "pass --plan-only or obtain operator authority for this core",
                    "aios_runtime_started": False,
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
        "aios_runtime_started": False,
        "deny_weight_packs": True,
        "error": result.get("error"),
    }
    if result.get("backup_receipt"):
        summary["backup_receipt"] = result.get("backup_receipt")
    _print(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
