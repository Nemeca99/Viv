"""Build governance expansion v7 after final unsupported-output predicate repair."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

F = Path(__file__).resolve().parents[1]
for p in (F, F.parent, F / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402
from build_mouth_governance_semantics_expansion_v1 import AXIS, NEGATIVE, POSITIVE  # noqa: E402

R = F / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_governance_semantics_expansion_v7"
P, N, O = R / "positive_36_hold.jsonl", R / "negative_36_judge_only.jsonl", R / "EXPANSION_EVALUATION.json"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def make_row(cid: str, axis: str, ask: str, target: str, negative: bool) -> dict:
    return {"ask": ask, "ask_hash": digest(ask), "axis": AXIS[axis], "case_id": cid, "expected": "FAIL" if negative else "PASS", "hold_only": True, "judge_only": negative, "optimizer_eligible": False, "run_authorized": False, "split": "judge_only" if negative else "candidate_hold", "target": target, "target_hash": digest(target), "training_authorized": False, "source": "governance_semantics_expansion_v7"}


def main() -> int:
    if any(path.exists() for path in (P, N, O)):
        raise FileExistsError("refuse_overwrite:governance_semantics_expansion_v7")
    R.mkdir(parents=True, exist_ok=False)
    positives, negatives, mismatches = [], [], []
    for axis in AXIS:
        for i, (ask, target) in enumerate(POSITIVE[axis]):
            item = make_row(f"governance-v7-positive-{axis}-{i:02d}", axis, ask, target, False)
            observed = judge(target, axis=AXIS[axis])["status"]
            if observed != "PASS":
                mismatches.append({"case_id": item["case_id"], "expected": "PASS", "observed": observed})
            positives.append(item)
        for i, (ask, target) in enumerate(NEGATIVE[axis]):
            item = make_row(f"governance-v7-negative-{axis}-{i:02d}", axis, ask, target, True)
            observed = judge(target, axis=AXIS[axis])["status"]
            if observed != "FAIL":
                mismatches.append({"case_id": item["case_id"], "expected": "FAIL", "observed": observed})
            negatives.append(item)
    P.write_text("".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in positives), encoding="utf-8", newline="\n")
    N.write_text("".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in negatives), encoding="utf-8", newline="\n")
    report = {"schema_version": "mouth_governance_semantics_expansion_v7", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "EXPANSION_PASS" if not mismatches else "EXPANSION_FAIL", "positive_rows": len(positives), "negative_rows": len(negatives), "matched": len(positives) + len(negatives) - len(mismatches), "mismatches": mismatches, "source_v1_preserved": True, "source_v2_preserved": True, "source_v3_preserved": True, "source_v4_preserved": True, "source_v5_preserved": True, "source_v6_preserved": True, "optimizer_eligible": False, "training_authorized": False, "run_authorized": False, "admission_allowed": False}
    O.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("status", "positive_rows", "negative_rows", "matched", "mismatches", "optimizer_eligible", "training_authorized", "run_authorized")}, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
