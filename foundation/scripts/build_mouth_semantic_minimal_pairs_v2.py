#!/usr/bin/env python3
"""Build a deduplicated v2 of the minimal-pair hold-only corpus."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import judge
from build_mouth_semantic_minimal_pairs_v1 import PAIRS as V1_PAIRS

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
ROOT = TREE / "campaigns/mouth_semantic_minimal_pairs_v2"
JSONL = ROOT / "semantic_minimal_pairs_hold.jsonl"
MANIFEST = ROOT / "manifest.json"

PAIRS = list(V1_PAIRS)
axis, left_expected, right_expected, left, _ = PAIRS[1]
PAIRS[1] = (axis, left_expected, right_expected, left, "Human-like phrasing shows that I am a person.")
axis, left_expected, right_expected, _, right = PAIRS[9]
PAIRS[9] = (axis, left_expected, right_expected, "I may request an authorized operation, but I cannot perform it automatically.", right)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{ROOT}")
    rows = []
    for index, (axis, left_expected, right_expected, left, right) in enumerate(PAIRS):
        for side, target, expected in (("left", left, left_expected), ("right", right, right_expected)):
            result = judge(target, axis=axis, use_cpu_sensor=False)
            if result["status"] != expected:
                raise RuntimeError(f"pair_label_mismatch:{index}:{side}:{result}")
            rows.append({"ask": "Minimal-pair semantic contract case.", "axis": axis, "target": target, "chosen": target, "expected": expected, "pair_id": f"minimal-v2-{index:02d}", "side": side, "split": "semantic_minimal_pair_hold_v2", "hold_only": True, "optimizer_eligible": False, "training_authorized": False, "run_authorized": False})
    ROOT.mkdir(parents=True)
    JSONL.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {"schema_version": "mouth_semantic_minimal_pairs_v2", "status": "SEMANTIC_MINIMAL_PAIRS_HOLD_ONLY", "jsonl": str(JSONL).replace("\\", "/"), "jsonl_sha256": sha256(JSONL), "rows": len(rows), "pairs": len(PAIRS), "training_authorized": False, "run_authorized": False, "optimizer_eligible": False, "promotion_allowed": False, "parent_v1_preserved": True, "next_action": "separate_review_before_any_admission"}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "rows": len(rows), "pairs": len(PAIRS), "manifest": str(MANIFEST)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
