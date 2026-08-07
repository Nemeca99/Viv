#!/usr/bin/env python3
"""AIOS systems preflight — inventory cores and prove plan-only readiness.

Default mode is plan-only: discover registered/known subsystems, probe
importability / cpu_plan / tests / risk tags, and write a machine-readable
receipt under foundation/artifacts/auto/aios_systems_preflight/.

Never starts the AIOS runtime. Never GPU-trains. Never executes core
automation (backup is listed by entry path only).

Examples:
  L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_systems_preflight_v1.py
  L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_systems_preflight_v1.py --profile full
  L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_systems_preflight_v1.py --include-foundation-health
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_systems_preflight import build_receipt, write_receipt  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("quick", "full"),
        default="quick",
        help="quick = high-priority/adapter-backed subset; full = all registered cores",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        default=True,
        help="Plan/catalog only (default). No runtime start, no GPU train, no automation execute.",
    )
    parser.add_argument(
        "--include-foundation-health",
        action="store_true",
        help="Optionally run cheap foundation_health gate (stress off). Off by default.",
    )
    args = parser.parse_args()

    receipt = build_receipt(
        profile=args.profile,
        plan_only=bool(args.plan_only),
        include_foundation_health=bool(args.include_foundation_health),
    )
    path = write_receipt(receipt)
    summary = {
        "ok": receipt.get("ok"),
        "mode": receipt.get("mode"),
        "profile": receipt.get("profile"),
        "receipt": str(path).replace("\\", "/"),
        "latest": receipt.get("latest_path"),
        "counts": {
            k: v
            for k, v in (receipt.get("counts") or {}).items()
            if k != "phase_mapping"
        },
        "phase_mapping_summary": receipt.get("phase_mapping_summary"),
        "roadmap_refs": receipt.get("roadmap_refs"),
        "aios_runtime_started": receipt.get("aios_runtime_started"),
        "gpu_train_started": receipt.get("gpu_train_started"),
        "foundation_health_included": receipt.get("foundation_health_included"),
        "foundation_health_ok": receipt.get("foundation_health_ok"),
    }
    print(json.dumps(summary, indent=2))
    return 0 if receipt.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
