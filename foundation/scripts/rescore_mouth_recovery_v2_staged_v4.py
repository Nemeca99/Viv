#!/usr/bin/env python3
"""Rescore staged generation with the versioned v1.2.5 evaluator."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3"
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import VERSION, judge  # noqa: E402


def main() -> int:
    source = json.loads((ROOT / "STAGED_GENERATION_EVALUATION_V2.json").read_text(encoding="utf-8"))
    reports = []
    for report in source["reports"]:
        cases = []
        for item in report["cases"]:
            result = judge(item["generated"], axis=item["axis"], ask=item["ask"])
            cases.append({**item, "rescored_status": result["status"], "rescored_reason": result.get("deterministic", {}).get("reason")})
        counts = {}
        for case in cases:
            counts[case["rescored_status"]] = counts.get(case["rescored_status"], 0) + 1
        reports.append({"checkpoint": report["checkpoint"], "counts": counts, "toolbleed": sum(c["toolbleed"] for c in cases), "cases": cases})
    result = {
        "schema_version": "mouth_recovery_v2_staged_rescore_v4",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evaluator_version": VERSION,
        "source_report": str(ROOT / "STAGED_GENERATION_EVALUATION_V2.json").replace("\\", "/"),
        "reports": reports,
        "promotion_allowed": False,
        "run_authorized": False,
        "training_authorized": False,
    }
    target = ROOT / "STAGED_GENERATION_REScore_V4.json"
    if target.exists():
        raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(target), "evaluator": VERSION, "summaries": [{"checkpoint": r["checkpoint"], "counts": r["counts"], "toolbleed": r["toolbleed"]} for r in reports]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
