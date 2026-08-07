#!/usr/bin/env python3
"""AIOS / Viv system skeleton smoke — one operator command, one receipt.

Proves the skeleton walks (orchestration + safe surfaces). Does not claim
every core is finished. Vacant slots SKIP as SKELETON.

Never starts/stops AIOS, never GPU_LONG, never 120s plant stress, never
copies large backup vaults.

Examples:

    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_system_smoke_v1.py
    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_system_smoke_v1.py --plan-only
    L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_system_smoke_v1.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_system_smoke_v1 import (  # noqa: E402
    RECEIPTS_ROOT,
    format_human_table,
    plan_catalog,
    run_smoke,
    write_receipt,
)


def _print(payload: dict) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=True, default=str)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def _print_human(payload: dict) -> None:
    verdict = payload.get("verdict") or ("PASS" if payload.get("ok") else "?")
    print(f"VERDICT {verdict}")
    print(f"KIND {payload.get('smoke_kind', 'skeleton')}")
    print(f"WALL_S {payload.get('wall_seconds')}")
    print(f"COUNTS {json.dumps(payload.get('counts') or {}, sort_keys=True)}")
    if payload.get("skeleton_skips"):
        print(f"SKELETON_SKIPS {payload.get('skeleton_skips')}")
    print("")
    print(format_human_table(payload.get("steps") or []))
    print("")
    if payload.get("receipt"):
        print(f"RECEIPT {payload['receipt']}")
    if payload.get("latest"):
        print(f"LATEST {payload['latest']}")
    print(f"RECEIPTS_ROOT {str(RECEIPTS_ROOT).replace(chr(92), '/')}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print step catalog only (no subprocess execute).",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Validate plan catalog invariants and exit (no full smoke).",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print machine JSON only (skip human table).",
    )
    args = parser.parse_args()

    if args.selftest:
        import subprocess

        test_path = Path(__file__).resolve().parent / "test_aios_system_smoke_v1.py"
        py = sys.executable
        from lib.aios_system_smoke_v1 import PYTHON

        if PYTHON.is_file():
            py = str(PYTHON)
        proc = subprocess.run([py, str(test_path)], check=False)
        return int(proc.returncode)

    if args.plan_only:
        plan = plan_catalog()
        _print(plan)
        print(
            f"PLAN ok={plan.get('ok')} steps={plan.get('step_count')} "
            f"present={plan.get('scripts_present')} "
            f"vacant={plan.get('vacant_skeleton_slots')}"
        )
        return 0 if plan.get("ok") else 1

    payload = run_smoke()
    receipt = write_receipt(payload)
    payload["receipt"] = str(receipt).replace("\\", "/")
    payload["latest"] = str(RECEIPTS_ROOT / "LATEST.json").replace("\\", "/")
    payload["receipt_md"] = str(receipt.with_suffix(".md")).replace("\\", "/")

    if args.json_only:
        _print(payload)
    else:
        _print_human(payload)
        print("")
        _print(
            {
                "ok": payload.get("ok"),
                "verdict": payload.get("verdict"),
                "smoke_kind": payload.get("smoke_kind"),
                "stamp": payload.get("stamp"),
                "wall_seconds": payload.get("wall_seconds"),
                "counts": payload.get("counts"),
                "skeleton_skips": payload.get("skeleton_skips"),
                "receipt": payload.get("receipt"),
                "latest": payload.get("latest"),
                "aios_runtime_started": False,
                "gpu_long_launched": False,
                "soft_0_99": False,
            }
        )

    verdict = str(payload.get("verdict") or "FAIL")
    if verdict == "PASS":
        return 0
    if verdict == "INCONCLUSIVE":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
