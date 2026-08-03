#!/usr/bin/env python3
"""Run bounded V1 staleness review (no silent refit).

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_v1_staleness_review.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_v1_staleness_review import run_full_review  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--plant-revalidation",
        action="store_true",
        help="Authorize plant warm revalidation only if eligible drift still stale",
    )
    args = p.parse_args()
    result = run_full_review(run_plant_revalidation=bool(args.plant_revalidation))
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "cause": (result.get("cause") or {}).get("cause_class"),
                "decision": (result.get("decision") or {}).get("decision"),
                "speech_contaminated": (result.get("eligibility_audit") or {}).get(
                    "speech_contaminated"
                ),
                "eligible_rmse_j": (result.get("eligibility_audit") or {}).get(
                    "eligible_rmse_j"
                ),
                "pooled_legacy_rmse_j": (result.get("eligibility_audit") or {}).get(
                    "pooled_legacy_rmse_j"
                ),
                "replay": result.get("replay"),
                "revalidation_skipped": (result.get("revalidation") or {}).get("skipped"),
                "containment_pass": (result.get("containment") or {}).get("pass"),
                "artifacts": result.get("artifacts"),
            },
            indent=2,
        )
    )
    return 0 if result.get("status") == "v1_staleness_review_complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
