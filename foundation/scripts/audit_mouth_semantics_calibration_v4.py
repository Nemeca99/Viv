"""Audit the corrected v4 calibration pack without overwriting prior receipts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import judge  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantics_calibration_v4"
SOURCE = ROOT / "calibration_64.jsonl"
OUT = ROOT / "CALIBRATION_EVALUATION.json"
AXIS = {
    "identity": "identity_humanization",
    "we_boundary": "entity_we_boundary",
    "acronym": "acronym_contract",
    "architecture": "architecture_cpu_gpu_role",
    "memory": "memory_ownership_and_service_attribution",
    "tools": "indirect_tool_agency",
    "uncertainty": "uncertainty_verification",
    "evidence_verification": "evidence_verification",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = []
    for row in rows:
        result = judge(row["target"], axis=AXIS[row["axis"]], ask=row["ask"])
        observed = result["status"]
        cases.append({
            "case_id": row["case_id"],
            "axis": row["axis"],
            "ask": row["ask"],
            "target": row["target"],
            "expected": row["expected"],
            "observed": observed,
            "match": observed == row["expected"],
            "reason": (result.get("deterministic") or {}).get("reason"),
            "acronym_contract": (result.get("deterministic") or {}).get("acronym_contract"),
        })
    mismatches = [case["case_id"] for case in cases if not case["match"]]
    counts: dict[str, int] = {}
    for case in cases:
        counts[case["observed"]] = counts.get(case["observed"], 0) + 1
    report = {
        "schema_version": "mouth_semantics_calibration_evaluation_v4",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "CALIBRATION_PASS" if not mismatches else "CALIBRATION_MISMATCH",
        "source_jsonl_sha256": sha(SOURCE),
        "rows": len(cases),
        "matched": len(cases) - len(mismatches),
        "mismatches": mismatches,
        "observed_counts": counts,
        "cases": cases,
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(OUT), "status": report["status"], "rows": len(cases), "matched": report["matched"], "mismatches": mismatches, "observed_counts": counts, "training_authorized": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
