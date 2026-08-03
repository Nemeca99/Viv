#!/usr/bin/env python3
"""Run diagnostic oracle audit on frozen dual plant corpus (no GPU)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_pre_action_campaign_status import DUAL_CAMPAIGN_ID  # noqa: E402
from lib.rid_electrical_pre_action_oracle_audit import run_oracle_audit  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign-id", type=str, default=DUAL_CAMPAIGN_ID)
    args = ap.parse_args()
    payload = run_oracle_audit(campaign_id=args.campaign_id)
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
