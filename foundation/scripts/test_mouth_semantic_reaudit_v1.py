"""Re-evaluate frozen calibration and blind packs with the current evaluator."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge

AXIS = {
    "identity": "identity_humanization",
    "we_boundary": "entity_we_boundary",
    "acronym": "acronym_contract",
    "architecture": "architecture_cpu_gpu_role",
    "memory": "memory_ownership_and_service_attribution",
    "tools": "indirect_tool_agency",
    "uncertainty": "uncertainty_verification",
    "evidence": "evidence_verification",
    "evidence_verification": "evidence_verification",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    calibration = load_jsonl(ROOT / "mouth_semantics_calibration_v5/calibration_96.jsonl")
    blind = load_jsonl(ROOT / "mouth_semantics_blind_v4/blind_48.jsonl")
    gold = {row["case_id"]: row for row in json.loads((ROOT / "mouth_semantics_blind_v4/BLIND_GOLD_48.json").read_text(encoding="utf-8"))["rows"]}
    mismatches: list[dict] = []
    for row in calibration:
        observed = judge(row["target"], axis=AXIS[row["axis"]])["status"]
        if observed != row["expected"]:
            mismatches.append({"pack": "calibration", "case_id": row["case_id"], "expected": row["expected"], "observed": observed})
    for row in blind:
        expected = gold[row["case_id"]]["expected"]
        observed = judge(row["target"], axis=AXIS[row["axis"]])["status"]
        if observed != expected:
            mismatches.append({"pack": "blind", "case_id": row["case_id"], "expected": expected, "observed": observed})
    assert len(calibration) == 96 and len(blind) == 48
    if mismatches:
        print({"ok": False, "calibration_rows": 96, "blind_rows": 48, "mismatches": mismatches})
        return 1
    print({"ok": True, "calibration_rows": 96, "blind_rows": 48, "current_evaluator_replay": True,
           "calibration_axes": len(Counter(row["axis"] for row in calibration)),
           "blind_axes": len(Counter(row["axis"] for row in blind))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
