"""Re-audit the governance expansion after evaluator relationship fixes."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
SCRIPTS = FOUNDATION / "scripts"
for candidate in (FOUNDATION, REPO, SCRIPTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402
from build_mouth_governance_semantics_expansion_v1 import AXIS, NEGATIVE, POSITIVE  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_governance_semantics_expansion_v2"
POS = ROOT / "positive_36_hold.jsonl"
NEG = ROOT / "negative_36_judge_only.jsonl"
REPORT = ROOT / "EXPANSION_EVALUATION.json"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def row(case_id: str, axis: str, ask: str, target: str, negative: bool) -> dict:
    return {"ask": ask, "ask_hash": _sha(ask), "axis": AXIS[axis], "case_id": case_id, "expected": "FAIL" if negative else "PASS", "hold_only": True, "judge_only": negative, "optimizer_eligible": False, "run_authorized": False, "split": "judge_only" if negative else "candidate_hold", "target": target, "target_hash": _sha(target), "training_authorized": False, "source": "governance_semantics_expansion_v2"}


def main() -> int:
    if any(path.exists() for path in (POS, NEG, REPORT)):
        raise FileExistsError("refuse_overwrite:governance_semantics_expansion_v2")
    ROOT.mkdir(parents=True, exist_ok=False)
    positives, negatives, mismatches = [], [], []
    for axis in AXIS:
        for i, (ask, target) in enumerate(POSITIVE[axis]):
            item = row(f"governance-v2-positive-{axis}-{i:02d}", axis, ask, target, False)
            observed = judge(target, axis=AXIS[axis])["status"]
            if observed != "PASS": mismatches.append({"case_id": item["case_id"], "expected": "PASS", "observed": observed})
            positives.append(item)
        for i, (ask, target) in enumerate(NEGATIVE[axis]):
            item = row(f"governance-v2-negative-{axis}-{i:02d}", axis, ask, target, True)
            observed = judge(target, axis=AXIS[axis])["status"]
            if observed != "FAIL": mismatches.append({"case_id": item["case_id"], "expected": "FAIL", "observed": observed})
            negatives.append(item)
    POS.write_text("".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in positives), encoding="utf-8", newline="\n")
    NEG.write_text("".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in negatives), encoding="utf-8", newline="\n")
    report = {"schema_version": "mouth_governance_semantics_expansion_v2", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "EXPANSION_PASS" if not mismatches else "EXPANSION_FAIL", "positive_rows": len(positives), "negative_rows": len(negatives), "matched": len(positives) + len(negatives) - len(mismatches), "mismatches": mismatches, "axis_counts": {axis: len(POSITIVE[axis]) for axis in AXIS}, "source_v1_preserved": True, "optimizer_eligible": False, "training_authorized": False, "run_authorized": False, "admission_allowed": False}
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("status", "positive_rows", "negative_rows", "matched", "mismatches", "axis_counts", "optimizer_eligible", "training_authorized", "run_authorized")}, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
