#!/usr/bin/env python3
"""Run offline pre_action energy training from frozen corpus."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_pre_action_campaign_status import DUAL_CAMPAIGN_ID  # noqa: E402
from lib.rid_electrical_pre_action_train import (  # noqa: E402
    run_dual_offline_training,
    run_offline_training,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign-id", type=str, default=DUAL_CAMPAIGN_ID)
    ap.add_argument("--dual", action="store_true", default=False)
    args = ap.parse_args()
    dual = args.dual or str(args.campaign_id).startswith("pre_action_energy_dual")
    if dual:
        report = run_dual_offline_training(write=True, campaign_id=args.campaign_id)
    else:
        report = run_offline_training(write=True, campaign_id=args.campaign_id)
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "status": report.get("status"),
                "winner": report.get("winner"),
                "admission": report.get("admission"),
                "gross": (report.get("gross") or {}).get("status"),
                "net": (report.get("net") or {}).get("status"),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
