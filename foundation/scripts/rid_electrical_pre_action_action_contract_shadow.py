#!/usr/bin/env python3
"""Prospective shadow for Action Contract campaign (only if g+h admitted)."""
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
from lib.rid_electrical_pre_action_paths import plant_dir  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign-id", type=str, default=ACTION_CONTRACT_CAMPAIGN_ID)
    args = ap.parse_args()
    root = plant_dir(args.campaign_id)
    train_path = root / "pre_action_action_contract_train_latest.json"
    if not train_path.exists():
        print(json.dumps({"ok": False, "status": "missing_train_artifact"}))
        return 1
    train = json.loads(train_path.read_text(encoding="utf-8"))
    if not train.get("candidate_for_separate_review"):
        out = {
            "ok": True,
            "status": "shadow_withheld_training_not_justified",
            "campaign_id": args.campaign_id,
            "candidate_for_separate_review": False,
            "deployable": False,
            "authority": {
                "learning_admission_withheld": True,
                "auto_admit": False,
                "auto_refit": False,
                "master_routing_authorized": False,
                "gates_action": False,
            },
        }
        path = root / "pre_action_shadow_validation_latest.json"
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(json.dumps(out, indent=2))
        return 0
    # Admitted path: mark candidate_for_separate_review only; do not auto-admit.
    # Full live shadow collection is operator-gated separately (no auto GPU fanout).
    out = {
        "ok": True,
        "status": "candidate_for_separate_review",
        "campaign_id": args.campaign_id,
        "candidate_for_separate_review": True,
        "deployable": False,
        "note": (
            "g+h admitted offline. Prospective live shadow requires explicit "
            "operator-run collection; not auto-started."
        ),
        "authority": {
            "learning_admission_withheld": True,
            "auto_admit": False,
            "auto_refit": False,
            "master_routing_authorized": False,
            "gates_action": False,
        },
    }
    path = root / "pre_action_shadow_validation_latest.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
