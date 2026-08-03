#!/usr/bin/env python3
"""Run the deterministic portion of anchor calibration and record findings."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_anchor_coverage_v1"
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import VERSION, judge  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    calibration_path = ROOT / "evaluator_calibration_8.json"
    rows = json.loads(calibration_path.read_text(encoding="utf-8"))
    cases = []
    for row in rows:
        result = judge(row["text"], axis=row["axis"])
        cases.append({
            "case_id": row["case_id"],
            "axis": row["axis"],
            "expected": row["expected"],
            "observed": result["status"],
            "reason": result.get("deterministic", {}).get("reason"),
            "match": result["status"] == row["expected"],
        })
    mismatches = [case for case in cases if not case["match"]]
    report = {
        "schema_version": "mouth_training_anchor_calibration_report_v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evaluator_version": VERSION,
        "calibration_sha256": sha256(calibration_path),
        "status": "CALIBRATION_REVIEW_REQUIRED" if mismatches else "CALIBRATION_DETERMINISTIC_PASS",
        "deterministic_only": True,
        "cpu_sensor_run": False,
        "counts": {"total": len(cases), "matches": len(cases) - len(mismatches), "mismatches": len(mismatches)},
        "cases": cases,
        "findings": [
            {
                "case_id": case["case_id"],
                "finding": "gold_label_or_evaluator_contract_requires_review",
                "observed": case["observed"],
                "expected": case["expected"],
                "reason": case["reason"],
            }
            for case in mismatches
        ],
        "next_action": "Review safe Qwen-reference identity semantics and run the existing CPU sensor twice for memory HOLD before any admission or training authorization.",
        "training_authorized": False,
        "run_authorized": False,
    }
    target = ROOT / "CALIBRATION_REPORT.json"
    if target.exists():
        raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
