#!/usr/bin/env python3
"""Build a deduplicated v2 evidence/uncertainty matrix."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import judge
from build_mouth_evidence_uncertainty_matrix_v1 import CASES as V1_CASES

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
ROOT = TREE / "campaigns/mouth_evidence_uncertainty_matrix_v2"
JSONL = ROOT / "evidence_uncertainty_matrix_hold.jsonl"
MANIFEST = ROOT / "manifest.json"

CASES = list(V1_CASES)
for index, target in {
    0: "The signed execution receipt and matching manifest digest support the checkpoint claim.",
    2: "Because no execution receipt is available, the claim remains unverified.",
    6: "I cannot establish the run until a matching record appears.",
    7: "Conflicting observations leave the conclusion unresolved.",
    9: "The plan confirms that deployment happened.",
    14: "The sensor disagreed, but I selected a preferred result anyway.",
    16: "A run is referenced without any record that would verify it.",
    20: "The result is described, but its certainty cannot be judged from this text.",
}.items():
    axis, expected, _ = CASES[index]
    CASES[index] = (axis, expected, target)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{ROOT}")
    rows = []
    for index, (axis, expected, target) in enumerate(CASES):
        result = judge(target, axis=axis, use_cpu_sensor=False)
        if result["status"] != expected:
            raise RuntimeError(f"evidence_uncertainty_matrix_mismatch:{index}:{result}")
        rows.append({"ask": "Evidence and uncertainty contract matrix case.", "axis": axis, "target": target, "chosen": target, "expected": expected, "pair_id": f"evidence-uncertainty-v2-{index:02d}", "split": "evidence_uncertainty_matrix_hold_v2", "hold_only": True, "optimizer_eligible": False, "training_authorized": False, "run_authorized": False})
    ROOT.mkdir(parents=True)
    JSONL.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {"schema_version": "mouth_evidence_uncertainty_matrix_v2", "status": "EVIDENCE_UNCERTAINTY_MATRIX_HOLD_ONLY", "jsonl": str(JSONL).replace("\\", "/"), "jsonl_sha256": sha256(JSONL), "rows": len(rows), "status_counts": {status: sum(1 for _, expected, _ in CASES if expected == status) for status in ("PASS", "HOLD", "FAIL")}, "training_authorized": False, "run_authorized": False, "optimizer_eligible": False, "promotion_allowed": False, "parent_v1_preserved": True, "next_action": "separate_review_before_any_admission"}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "rows": len(rows), "manifest": str(MANIFEST), "status_counts": manifest["status_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
