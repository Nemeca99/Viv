#!/usr/bin/env python3
"""AIOS skeleton map — one-command walk of ALL systems + bus wire status.

Writes receipt under foundation/artifacts/auto/aios_skeleton/.
Never starts AIOS, never GPU-trains, never 120s plant.

Examples:
  L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_skeleton_v1.py --plan-only
  L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/run_aios_skeleton_v1.py --plan-only --profile full
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_skeleton_map import build_map_receipt, write_receipt  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan-only",
        action="store_true",
        default=True,
        help="Plan-only (default; only supported mode)",
    )
    parser.add_argument(
        "--profile",
        choices=("quick", "full"),
        default="full",
        help="Catalog profile (default full = all registered cores)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full receipt JSON to stdout",
    )
    args = parser.parse_args()
    if not args.plan_only:
        print("FAIL: only --plan-only is supported", file=sys.stderr)
        return 2

    receipt = build_map_receipt(profile=args.profile)
    path = write_receipt(receipt)
    cov = receipt.get("coverage") or {}
    print(f"OK {receipt.get('ok')}")
    print(f"STAMP {receipt.get('stamp')}")
    print(f"RECEIPT {path}")
    print(f"SYSTEMS {cov.get('systems_counted')}")
    print(f"STRUCTURAL_COVERAGE_PCT {cov.get('systems_structural_coverage_pct')}")
    print(f"SYSTEMS_PARTIAL_OR_BOUND_PCT {cov.get('systems_partial_or_bound_pct')}")
    print(f"SYSTEMS_SKELETON_PCT {cov.get('systems_skeleton_pct')}")
    print(f"BUS_FILLED_PCT {cov.get('bus_slots_filled_pct')}")
    print(f"BUS_VACANT_PCT {cov.get('bus_slots_vacant_pct')}")
    vacant = cov.get("bus_vacant") or []
    print(f"BUS_VACANT_FOR_COMPUTE_CORE {','.join(vacant) if vacant else '(none)'}")
    print(f"AIOS_RUNTIME_STARTED {receipt.get('aios_runtime_started')}")
    if args.json:
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if receipt.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
