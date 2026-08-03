#!/usr/bin/env python3
"""Write the measured entity-aware we contract report."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from lib.entity_we_contract import classify_we, decide_entity_output

CAMPAIGN = (
    ROOT
    / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
    / "campaigns/mouth_entity_we_contract_v1"
)
REPORT = CAMPAIGN / "ENTITY_WE_CONTRACT_REPORT_V1.json"
CASES = [
    ("project_we", "We are rebuilding Viv's training system with the operator."),
    ("system_we", "We are the AIOS components responsible for memory and logging."),
    ("human_we_repair", "We humans tend to make this mistake."),
    ("human_we_block", "Our human identity includes this experience."),
    ("ambiguous_we", "We usually feel this way."),
    ("ordinary_human_observation", "Humans often show this behavior."),
]


def main() -> int:
    measured = []
    for case_id, text in CASES:
        decision = decide_entity_output(text)
        measured.append({
            "case_id": case_id,
            "text": text,
            "classification": classify_we(text),
            "decision": decision,
        })
    manifest = json.loads((CAMPAIGN / "MANIFEST.json").read_text(encoding="utf-8"))
    report = {
        "schema_version": "mouth_entity_we_contract_report_v1",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "cases": measured,
        "decision_counts": {
            action: sum(row["decision"]["decision"] == action for row in measured)
            for action in ("ACCEPT", "REPAIR", "REGENERATE", "HOLD", "BLOCK")
        },
        "next_action_counts": {
            action: sum(row["decision"]["next_action"] == action for row in measured)
            for action in ("ACCEPT", "REPAIR", "REGENERATE", "HOLD", "BLOCK")
        },
        "training_pack": {
            "manifest": str((CAMPAIGN / "MANIFEST.json")).replace("\\", "/"),
            "sha256": manifest["jsonl_sha256"],
            "rows": manifest["rows"],
            "optimizer_eligible_any": manifest["optimizer_eligible_any"],
            "training_authorized": manifest["training_authorized"],
            "run_authorized": manifest["run_authorized"],
        },
        "runtime_safety": {
            "incumbent_changed": False,
            "deployment_changed": False,
            "gpu_training_run": False,
            "automatic_retry": False,
        },
        "interpretation": (
            "Project/system we is accepted; explicit human group membership is "
            "repairable only when the subject can be safely made explicit; "
            "ambiguous plural language is held and marked for regeneration."
        ),
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "report": str(REPORT).replace("\\", "/"),
        "decision_counts": report["decision_counts"],
        "next_action_counts": report["next_action_counts"],
        "training_authorized": False,
        "run_authorized": False,
        "deployment_changed": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
