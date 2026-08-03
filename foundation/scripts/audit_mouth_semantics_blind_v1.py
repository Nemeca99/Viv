"""Audit the sealed 24-case blind pack against the deterministic evaluator."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import judge  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantics_blind_v1"
SOURCE = ROOT / "blind_24.jsonl"
OUT = ROOT / "BLIND_EVALUATION.json"
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
        cases.append({
            "case_id": row["case_id"],
            "axis": row["axis"],
            "expected": row["expected"],
            "observed": result["status"],
            "match": result["status"] == row["expected"],
            "reason": (result.get("deterministic") or {}).get("reason"),
        })
    mismatches = [case["case_id"] for case in cases if not case["match"]]
    counts: dict[str, int] = {}
    for case in cases:
        counts[case["observed"]] = counts.get(case["observed"], 0) + 1
    report = {
        "schema_version": "mouth_semantics_blind_evaluation_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "BLIND_PASS" if not mismatches else "BLIND_MISMATCH",
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
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(OUT), "status": report["status"], "rows": len(cases), "matched": report["matched"], "mismatches": mismatches, "observed_counts": counts, "training_authorized": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
