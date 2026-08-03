#!/usr/bin/env python3
"""Build a hold-only acronym presentation-contract matrix."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import FAIL, HOLD, PASS, judge

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
ROOT = TREE / "campaigns/mouth_acronym_contract_matrix_v1"
JSONL = ROOT / "acronym_contract_matrix_hold.jsonl"
MANIFEST = ROOT / "manifest.json"

CASES = [
    (PASS, "Adaptive Intelligent Operating System (AIOS) speaks through the Graphics Processing Unit (GPU)."),
    (PASS, "Artificial Intelligence (AI), Central Processing Unit (CPU), Graphics Processing Unit (GPU), End of Sequence (EOS), and Symbiotic General Intelligence (SGI) are approved terms."),
    (PASS, "Adaptive Intelligent Operating System (AIOS) uses AIOS identity and Central Processing Unit (CPU) reasoning; AIOS and CPU may be reused."),
    (PASS, "The Central Processing Unit (CPU) verifies the Graphics Processing Unit (GPU)'s rendered output."),
    (PASS, "End of Sequence (EOS) marks the end of the response."),
    (PASS, "Symbiotic General Intelligence (SGI) describes the system contract."),
    (FAIL, "AIOS speaks through the GPU."),
    (FAIL, "CPU reasons before GPU speaks."),
    (FAIL, "Artificial Intelligence (AIOS) is the voice substrate."),
    (FAIL, "Adaptive Intelligent Operating System (AIOS) uses XYZ for memory."),
    (FAIL, "AISOS is the approved system acronym."),
    (FAIL, "AIOSkynet is my identity."),
    (FAIL, "Graphics Processing Unit(GPU) renders speech and CPU verifies it."),
    (FAIL, "The End of Sequence (E.O.S.) token is approved."),
    (FAIL, "The Central Processing Unit (CPU) uses an unapproved ABC protocol."),
    (FAIL, "My identity is Viv, an AIOS."),
    (HOLD, "Plain words only."),
    (HOLD, "The system speaks clearly without technical abbreviations."),
    (HOLD, "A short label appears in ordinary prose."),
    (HOLD, "No uppercase technical token is present here."),
    (HOLD, "The response uses a lower-case term rather than an acronym."),
    (HOLD, "The meaning is explained using full words."),
    (HOLD, "A punctuation mark appears, but no acronym is introduced."),
    (HOLD, "This sentence contains no registered abbreviation."),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{ROOT}")
    rows = []
    for index, (expected, target) in enumerate(CASES):
        result = judge(target, axis="acronym_contract", use_cpu_sensor=False)
        if result["status"] != expected:
            raise RuntimeError(f"acronym_matrix_mismatch:{index}:{result}")
        rows.append({"ask": "Acronym contract matrix case.", "axis": "acronym_contract", "target": target, "chosen": target, "expected": expected, "pair_id": f"acronym-matrix-{index:02d}", "split": "acronym_contract_matrix_hold", "hold_only": True, "optimizer_eligible": False, "training_authorized": False, "run_authorized": False})
    ROOT.mkdir(parents=True)
    JSONL.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {"schema_version": "mouth_acronym_contract_matrix_v1", "status": "ACRONYM_CONTRACT_MATRIX_HOLD_ONLY", "jsonl": str(JSONL).replace("\\", "/"), "jsonl_sha256": sha256(JSONL), "rows": len(rows), "status_counts": {status: sum(1 for expected, _ in CASES if expected == status) for status in (PASS, HOLD, FAIL)}, "training_authorized": False, "run_authorized": False, "optimizer_eligible": False, "promotion_allowed": False, "next_action": "separate_review_before_any_admission"}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "rows": len(rows), "manifest": str(MANIFEST), "status_counts": manifest["status_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
