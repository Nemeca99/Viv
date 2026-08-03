#!/usr/bin/env python3
"""Run prospective shadow harness (synthetic or plant dual)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_pre_action_campaign_status import DUAL_CAMPAIGN_ID  # noqa: E402
from lib.rid_electrical_pre_action_shadow import (  # noqa: E402
    run_plant_dual_shadow_campaign,
    run_synthetic_shadow_campaign,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--plant", action="store_true")
    ap.add_argument("--campaign-id", type=str, default=DUAL_CAMPAIGN_ID)
    args = ap.parse_args()
    if args.plant:
        out = run_plant_dual_shadow_campaign(campaign_id=args.campaign_id, write=True)
    else:
        out = run_synthetic_shadow_campaign(write=True)
    print(
        json.dumps(
            {
                "ok": out.get("ok"),
                "status": out.get("status"),
                "passed": out.get("passed"),
                "protocol_checks": out.get("protocol_checks"),
                "n_eligible": out.get("n_eligible"),
                "gross": (out.get("gross") or {}).get("n_eligible"),
                "net": (out.get("net") or {}).get("n_eligible"),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if out.get("ok") is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
