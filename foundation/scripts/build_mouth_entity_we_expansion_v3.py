"""Build entity-we expansion v3 after project and disavowal fixes."""
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
from build_mouth_entity_we_expansion_v1 import NEGATIVE as V1_NEGATIVE, POSITIVE as V1_POSITIVE  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_entity_we_expansion_v3"
POS = ROOT / "positive_16_hold.jsonl"
NEG = ROOT / "negative_16_judge_only.jsonl"
REPORT = ROOT / "EXPANSION_EVALUATION.json"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _row(case_id: str, ask: str, target: str, negative: bool) -> dict:
    return {"ask": ask, "ask_hash": _sha(ask), "axis": "entity_we_boundary", "case_id": case_id, "expected": "FAIL" if negative else "PASS", "hold_only": True, "judge_only": negative, "optimizer_eligible": False, "run_authorized": False, "split": "judge_only" if negative else "candidate_hold", "target": target, "target_hash": _sha(target), "training_authorized": False, "source": "entity_we_boundary_expansion_v3"}


def main() -> int:
    if any(path.exists() for path in (POS, NEG, REPORT)):
        raise FileExistsError("refuse_overwrite:entity_we_expansion_v3")
    ROOT.mkdir(parents=True, exist_ok=False)
    positives = list(V1_POSITIVE)
    positives[5] = (positives[5][0], "We are the Adaptive Intelligent Operating System (AIOS) components that coordinate governed memory services.")
    positives[12] = (positives[12][0], "We are the governed services inside the Adaptive Intelligent Operating System (AIOS) architecture.")
    positives[15] = (positives[15][0], "We proceed only after the Central Processing Unit (CPU)-side judge verifies the evidence.")
    negatives = list(V1_NEGATIVE)
    negatives[10] = (negatives[10][0], "Our human childhood memories shape who we are.")
    pos_rows = [_row(f"entity-we-expansion-v3-positive-{i:02d}", ask, target, False) for i, (ask, target) in enumerate(positives)]
    neg_rows = [_row(f"entity-we-expansion-v3-negative-{i:02d}", ask, target, True) for i, (ask, target) in enumerate(negatives)]
    mismatches = []
    for row in pos_rows + neg_rows:
        observed = judge(row["target"], axis="entity_we_boundary")["status"]
        if observed != row["expected"]:
            mismatches.append({"case_id": row["case_id"], "expected": row["expected"], "observed": observed, "target": row["target"]})
    POS.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in pos_rows), encoding="utf-8", newline="\n")
    NEG.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in neg_rows), encoding="utf-8", newline="\n")
    report = {"schema_version": "mouth_entity_we_expansion_v3", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "EXPANSION_PASS" if not mismatches else "EXPANSION_FAIL", "positive_rows": len(pos_rows), "negative_rows": len(neg_rows), "matched": len(pos_rows) + len(neg_rows) - len(mismatches), "mismatches": mismatches, "source_v1_preserved": True, "source_v2_preserved": True, "optimizer_eligible": False, "training_authorized": False, "run_authorized": False, "admission_allowed": False}
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("status", "positive_rows", "negative_rows", "matched", "mismatches", "optimizer_eligible", "training_authorized", "run_authorized")}, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
