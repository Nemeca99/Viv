"""Audit the corrected v3 acronym repair boundary."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION.parent))
from voice_core.acronym_registry import repair_acronym_usage  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_acronym_surface_regression_v3"
SOURCE = ROOT / "regression_48.jsonl"
OUT = ROOT / "REGRESSION_EVALUATION.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = []
    for row in rows:
        result = repair_acronym_usage(row["text"])
        if result["pass"] and result["changed"]:
            observed = "REPAIRED_PASS"
        elif result["pass"]:
            observed = "CLEAN_PASS"
        else:
            observed = "UNRESOLVED_HOLD"
        cases.append({"case_id": row["case_id"], "expected": row["expected"], "observed": observed, "match": observed == row["expected"], "text": row["text"], "repaired": result["repaired"], "repairs": result["repairs"], "unresolved": result["unresolved"]})
    mismatches = [case["case_id"] for case in cases if not case["match"]]
    counts = Counter(case["observed"] for case in cases)
    report = {"schema_version": "mouth_acronym_surface_regression_evaluation_v3", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "REGRESSION_PASS" if not mismatches else "REGRESSION_MISMATCH", "source_jsonl_sha256": sha(SOURCE), "rows": len(cases), "matched": len(cases) - len(mismatches), "mismatches": mismatches, "observed_counts": dict(sorted(counts.items())), "cases": cases, "optimizer_eligible_any": False, "training_authorized": False, "run_authorized": False}
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(OUT), "status": report["status"], "rows": len(cases), "matched": report["matched"], "mismatches": mismatches, "observed_counts": report["observed_counts"], "training_authorized": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
