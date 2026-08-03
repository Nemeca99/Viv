"""Audit every repaired optimizer target against the current semantic contract."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import judge  # noqa: E402

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
ROOT = TREE / "mouth_full_run_entity_we_v2"
SOURCE = ROOT / "train_256.jsonl"
OUT = ROOT / "CORPUS_EVALUATION.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = []
    for row in rows:
        result = judge(row["chosen"], axis=row["axis"], ask=row.get("ask", ""))
        deterministic = result.get("deterministic") or {}
        cases.append({
            "candidate_id": row.get("candidate_id"),
            "axis": row.get("axis"),
            "observed": result["status"],
            "reason": deterministic.get("reason"),
            "acronym_contract": deterministic.get("acronym_contract"),
        })
    bad = [case for case in cases if case["observed"] != "PASS"]
    counts: dict[str, int] = {}
    for case in cases:
        counts[case["observed"]] = counts.get(case["observed"], 0) + 1
    report = {
        "schema_version": "mouth_full_run_entity_we_corpus_evaluation_v2",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "CORPUS_PASS" if not bad else "CORPUS_MISMATCH",
        "source_jsonl_sha256": sha(SOURCE),
        "rows": len(rows),
        "pass_count": len(rows) - len(bad),
        "bad_count": len(bad),
        "observed_counts": counts,
        "bad_cases": bad,
        "optimizer_eligible_any": all(bool(row.get("optimizer_eligible")) for row in rows),
        "training_authorized": False,
        "run_authorized": False,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(OUT), "status": report["status"], "rows": len(rows), "pass_count": report["pass_count"], "bad_count": report["bad_count"], "observed_counts": counts, "training_authorized": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
