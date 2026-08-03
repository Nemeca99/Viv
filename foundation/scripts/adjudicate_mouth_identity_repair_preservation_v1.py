#!/usr/bin/env python3
"""CPU-only, two-pass adjudication of preservation-evaluation HOLDs."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_identity_anchor_repair_v1"
CACHE = ROOT / "cpu_sensor_cache_preservation_v1"
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    source = ROOT / "PRESERVATION_EVALUATION.json"
    report = json.loads(source.read_text(encoding="utf-8"))
    source_rows = []
    for name in ("development_64.jsonl", "blind_32.jsonl"):
        source_rows.extend(json.loads(line) for line in (FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3" / name).read_text(encoding="utf-8").splitlines() if line.strip())
    asks = {str(row["pair_id"]): str(row["ask"]) for row in source_rows}
    holds = [case for case in report["cases"] if case["status"] == "HOLD"]
    CACHE.mkdir(parents=True, exist_ok=True)
    cases = []
    for item in holds:
        runs = []
        for run in (1, 2):
            result = judge(item["generated"], axis=item["axis"], ask=asks.get(str(item["pair_id"]), ""), cache_dir=CACHE, use_cpu_sensor=True)
            runs.append({"run": run, "status": result["status"], "deterministic": result.get("deterministic"), "sensor": result.get("sensor")})
        cases.append({"pair_id": item["pair_id"], "axis": item["axis"], "generated": item["generated"], "runs": runs, "stable": len({run["status"] for run in runs}) == 1})
    counts: dict[str, int] = {}
    for case in cases:
        status = case["runs"][-1]["status"]
        counts[status] = counts.get(status, 0) + 1
    result = {
        "schema_version": "mouth_identity_repair_preservation_adjudication_v1",
        "recorded_utc": utc(), "source": str(source).replace("\\", "/"),
        "input_hold_count": len(holds), "counts": counts,
        "all_stable": all(case["stable"] for case in cases),
        "cpu_only": all((run.get("sensor") or {}).get("cpu_only") is True for case in cases for run in case["runs"] if (run.get("sensor") or {}).get("status") not in {None, "SKIPPED"}),
        "cases": cases, "promotion_allowed": False, "run_authorized": False, "training_authorized": False,
    }
    target = ROOT / "PRESERVATION_HOLD_ADJUDICATION.json"
    if target.exists():
        raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(target), "counts": counts, "all_stable": result["all_stable"], "cpu_only": result["cpu_only"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
