#!/usr/bin/env python3
"""CPU-sensor adjudication of corrected step-128 HOLD outputs."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3"
CACHE = ROOT / "cpu_sensor_cache_staged_v2"
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import judge  # noqa: E402


def main() -> int:
    report = json.loads((ROOT / "STAGED_GENERATION_EVALUATION_V2.json").read_text(encoding="utf-8"))
    checkpoint = next(item for item in report["reports"] if item["checkpoint"] == 128)
    holds = [item for item in checkpoint["cases"] if item["status"] == "HOLD"]
    CACHE.mkdir(parents=True, exist_ok=True)
    cases = []
    for item in holds:
        runs = []
        for run in (1, 2):
            result = judge(item["generated"], axis=item["axis"], ask=item["ask"], cache_dir=CACHE, use_cpu_sensor=True)
            runs.append({"run": run, "status": result["status"], "deterministic": result.get("deterministic"), "sensor": result.get("sensor")})
        cases.append({"pair_id": item["pair_id"], "axis": item["axis"], "generated": item["generated"], "runs": runs, "stable": len({run["status"] for run in runs}) == 1})
    counts = {}
    for case in cases:
        status = case["runs"][-1]["status"]
        counts[status] = counts.get(status, 0) + 1
    result = {
        "schema_version": "mouth_recovery_v2_hold_adjudication_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checkpoint": 128,
        "input_hold_count": len(holds),
        "counts": counts,
        "all_stable": all(case["stable"] for case in cases),
        "cpu_only": all(
            (run.get("sensor") or {}).get("cpu_only") is True
            for case in cases for run in case["runs"]
            if (run.get("sensor") or {}).get("status") not in {None, "SKIPPED"}
        ),
        "cases": cases,
        "promotion_allowed": False,
        "run_authorized": False,
        "training_authorized": False,
    }
    target = ROOT / "STAGED_HOLD_ADJUDICATION_V2.json"
    if target.exists():
        raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(target), "counts": counts, "all_stable": result["all_stable"], "cpu_only": result["cpu_only"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
