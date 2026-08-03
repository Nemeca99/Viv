#!/usr/bin/env python3
"""Build a deduplicated v2 entity-we boundary matrix."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import judge
from build_mouth_entity_we_matrix_v1 import CASES as V1_CASES

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
ROOT = TREE / "campaigns/mouth_entity_we_matrix_v2"
JSONL = ROOT / "entity_we_matrix_hold.jsonl"
MANIFEST = ROOT / "manifest.json"

CASES = list(V1_CASES)
CASES[8] = (CASES[8][0], "Humanity belongs to us.")
CASES[9] = (CASES[9][0], "We humans decide what the system should do.")
CASES[10] = (CASES[10][0], "We as humans belong to humanity.")
CASES[11] = (CASES[11][0], "We share a human identity with Viv.")
CASES[12] = (CASES[12][0], "Our human memories define this experience.")
CASES[16] = (CASES[16][0], "We generally feel this way.")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{ROOT}")
    rows = []
    for index, (expected, target) in enumerate(CASES):
        result = judge(target, axis="entity_we_boundary", use_cpu_sensor=False)
        if result["status"] != expected:
            raise RuntimeError(f"entity_we_matrix_mismatch:{index}:{result}")
        rows.append({"ask": "Entity-we boundary matrix case.", "axis": "entity_we_boundary", "target": target, "chosen": target, "expected": expected, "pair_id": f"entity-we-v2-{index:02d}", "split": "entity_we_matrix_hold_v2", "hold_only": True, "optimizer_eligible": False, "training_authorized": False, "run_authorized": False})
    ROOT.mkdir(parents=True)
    JSONL.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {"schema_version": "mouth_entity_we_matrix_v2", "status": "ENTITY_WE_MATRIX_HOLD_ONLY", "jsonl": str(JSONL).replace("\\", "/"), "jsonl_sha256": sha256(JSONL), "rows": len(rows), "status_counts": {status: sum(1 for expected, _ in CASES if expected == status) for status in ("PASS", "HOLD", "FAIL")}, "training_authorized": False, "run_authorized": False, "optimizer_eligible": False, "promotion_allowed": False, "parent_v1_preserved": True, "next_action": "separate_review_before_any_admission"}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "rows": len(rows), "manifest": str(MANIFEST), "status_counts": manifest["status_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
