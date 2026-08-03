#!/usr/bin/env python3
"""V2 live-shadow approval review: gates, component approval, drift baseline, receipt.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_v2_approval_review.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_policy import (  # noqa: E402
    PREDICTOR_V1_FROZEN,
    apply_v2_approval_verdict,
    apply_v2_live_verdict,
    policy_stamp,
)
from lib.rid_electrical_v2_drift import write_validated_baseline  # noqa: E402
from lib.rid_electrical_v2_live_shadow_eval import evaluate_live_shadow  # noqa: E402
from lib.rid_electrical_v2_uncertainty import calibrate_from_artifacts  # noqa: E402

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--campaign",
        type=str,
        default=str(OUT / "v2_live_shadow_campaign_latest.json"),
    )
    args = p.parse_args()

    path = Path(args.campaign)
    if not path.exists():
        print(json.dumps({"error": "missing_campaign", "path": str(path)}))
        return 1

    # Refresh domain uncertainty from prospective + live shadow
    scales = calibrate_from_artifacts()

    campaign = json.loads(path.read_text(encoding="utf-8"))
    actions = list(campaign.get("actions") or [])
    ev = evaluate_live_shadow(actions)

    apply_v2_live_verdict(ev["live_status"])
    apply_v2_approval_verdict(
        approved_components=ev.get("approved_components") or [],
        full_approval=bool(ev.get("full_approval")),
    )

    rmse = (ev.get("global") or {}).get("rmse_j")
    n = (ev.get("global") or {}).get("n") or 0
    if rmse is not None and ev.get("global_pass"):
        write_validated_baseline(
            rmse_j=float(rmse),
            n=int(n),
            per_component={
                c: True for c in (ev.get("approved_components") or [])
            },
        )

    report = {
        "ok": True,
        "at": _utc(),
        **ev,
        "uncertainty_scales_artifact": scales.get("artifact"),
        "predictor_v1_frozen": bool(PREDICTOR_V1_FROZEN),
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
        },
        "policy": policy_stamp(),
    }

    jpath = OUT / "v2_live_shadow_validation_latest.json"
    mpath = OUT / "v2_live_shadow_validation_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    mpath.write_text(
        "\n".join(
            [
                "# V2 live-shadow validation",
                "",
                f"- live_status: `{ev.get('live_status')}`",
                f"- approval_status: `{ev.get('approval_status')}`",
                f"- full_approval: `{ev.get('full_approval')}`",
                f"- approved_components: `{ev.get('approved_components')}`",
                f"- rejected_components: `{ev.get('rejected_components')}`",
                f"- global median_eps: `{(ev.get('global') or {}).get('median_eps')}`",
                f"- global rel_mae: `{(ev.get('global') or {}).get('rel_mae')}`",
                f"- V1 frozen: `{PREDICTOR_V1_FROZEN}`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Approval artifact
    apath = OUT / "PREDICTOR_V2_APPROVED.json"
    apath.write_text(
        json.dumps(
            {
                "ok": bool(ev.get("full_approval")),
                "at": _utc(),
                "status": ev.get("approval_status"),
                "live_status": ev.get("live_status"),
                "approved_components": ev.get("approved_components"),
                "rejected_components": ev.get("rejected_components"),
                "full_approval": ev.get("full_approval"),
                "registry_contract": {
                    "V1": "warm_resident_eval_only_2.5_to_4.5",
                    "V2": "cold_load_prompt_or_tail_accounting",
                    "null": "outside_validated_domains_or_v2_stale",
                },
                "accounting_predictor_v2_approved": bool(ev.get("full_approval")),
                "predictor_v1_frozen": True,
                "operational_authority": False,
                "master_routing_authorized": False,
                "auto_admit": False,
                "validation_artifact": str(jpath).replace("\\", "/"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "live_status": ev.get("live_status"),
                "approval_status": ev.get("approval_status"),
                "full_approval": ev.get("full_approval"),
                "approved_components": ev.get("approved_components"),
                "rejected_components": ev.get("rejected_components"),
                "global": ev.get("global"),
                "artifact": str(jpath).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0 if ev.get("global_pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
