#!/usr/bin/env python3
"""Train Action Contract workload demand (g) then energy map (h). Offline only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_pre_action_campaign_status import (  # noqa: E402
    ACTION_CONTRACT_CAMPAIGN_ID,
)
from lib.rid_electrical_pre_action_workload_train import (  # noqa: E402
    run_action_contract_train,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign-id", type=str, default=ACTION_CONTRACT_CAMPAIGN_ID)
    args = ap.parse_args()
    out = run_action_contract_train(campaign_id=args.campaign_id)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
