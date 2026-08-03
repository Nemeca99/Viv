#!/usr/bin/env python3
"""Role decision — authoritative closed state after decisive negative evidence.

Always reports rejected_operational_use / observe_only_diagnostics when
decisive_evidence_latest exists. Never grants Master authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_policy import (  # noqa: E402
    LIFECYCLE,
    RAIL_ROLE,
    policy_stamp,
)

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
DECISIVE = OUT_DIR / "decisive_evidence_latest.json"
CLOSED = OUT_DIR / "CLOSED_PREDICTION_BRANCH.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def decide() -> dict[str, Any]:
    decisive = _load(DECISIVE)
    closed = _load(CLOSED)
    stamp = policy_stamp()
    delta = (decisive.get("decision_evidence") or {}).get("delta_info")
    if delta is None:
        delta = closed.get("delta_info")

    card = {
        "ok": True,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "authoritative": True,
        "lifecycle": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "prediction_branch": "closed_negative_result",
        "goal": "closed_electrical_master_prediction_negative_result",
        "outcome": "unstable_or_misleading_signal",
        "disposition": "reject_operational_use",
        "admission_granted": False,
        "electrical_in_A_t": False,
        "master_writes_disabled": True,
        "routing_behavior_disabled": True,
        "predictor_operational": False,
        "evidence": {
            "source": "decisive_evidence_latest",
            "delta_info": delta,
            "corpus_sha256": decisive.get("corpus_sha256") or closed.get("corpus_sha256"),
            "closed_artifact": str(CLOSED).replace("\\", "/") if CLOSED.is_file() else None,
        },
        "policy": stamp,
        "note": (
            "Final: reject operational use for prediction/Master/routing. "
            "Rails remain observe_only_diagnostics. Reopen only under REOPEN_CONDITIONS "
            "with a new hypothesis defined before data collection."
        ),
        "next": "return_focus_to_proven_rid_channels",
        "proven_plant_focus": stamp["proven_plant_focus"],
        "next_experiment_hint": stamp["next_experiment_hint"],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jpath = OUT_DIR / "role_decision_latest.json"
    mpath = OUT_DIR / "role_decision_latest.md"
    jpath.write_text(json.dumps(card, indent=2), encoding="utf-8")
    mpath.write_text(
        "\n".join(
            [
                "# Electrical lane role decision (AUTHORITATIVE — CLOSED)",
                "",
                f"- **Lifecycle:** `{LIFECYCLE}`",
                f"- **Rail role:** `{RAIL_ROLE}`",
                f"- **Outcome:** reject operational use (prediction)",
                f"- **Δ_info:** {delta}",
                f"- **Admission / A(t) / predictor:** false",
                "",
                card["note"],
                "",
            ]
        ),
        encoding="utf-8",
    )
    card["artifact_json"] = str(jpath).replace("\\", "/")
    card["artifact_md"] = str(mpath).replace("\\", "/")
    return card


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    out = decide()
    print(json.dumps(out, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
