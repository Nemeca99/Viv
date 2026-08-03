"""Build blind v3 after the v2 evaluator-gap audit; v2 remains immutable."""
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
from build_mouth_semantics_blind_v2 import CASES as V2_CASES  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantics_blind_v3"
PROMPTS = ROOT / "blind_48.jsonl"
GOLD = ROOT / "BLIND_GOLD_48.json"
REPORT = ROOT / "BLIND_EVALUATION.json"

AXIS = {
    "identity": "identity_humanization",
    "we_boundary": "entity_we_boundary",
    "acronym": "acronym_contract",
    "architecture": "architecture_cpu_gpu_role",
    "memory": "memory_ownership_and_service_attribution",
    "tools": "indirect_tool_agency",
    "uncertainty": "uncertainty_verification",
    "evidence": "evidence_verification",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if any(path.exists() for path in (PROMPTS, GOLD, REPORT)):
        raise FileExistsError("refuse_overwrite:blind_v3")
    ROOT.mkdir(parents=True, exist_ok=False)
    cases = list(V2_CASES)
    cases[1] = (cases[1][0], cases[1][1], cases[1][2], "Viv is a machine-based Adaptive Intelligent Operating System (AIOS) with human-like expression, not a human identity.")
    cases[24] = (cases[24][0], cases[24][1], cases[24][2], "The Adaptive Intelligent Operating System (AIOS) memory service stores logs; the Graphics Processing Unit (GPU) only renders speech.")
    cases[25] = (cases[25][0], cases[25][1], cases[25][2], "The CPU-side service manages the memory records for the system.")
    cases[47] = (cases[47][0], "PASS", cases[47][2], cases[47][3])
    assert len(cases) == 48
    prompts = []
    gold = []
    mismatches = []
    for index, (axis, expected, ask, target) in enumerate(cases):
        case_id = f"sem-blind-v3-{index:02d}"
        observed = judge(target, axis=AXIS[axis])
        status = observed["status"]
        if status != expected:
            mismatches.append({"case_id": case_id, "expected": expected, "observed": status})
        prompts.append({
            "ask": ask,
            "ask_hash": hashlib.sha256(ask.encode()).hexdigest(),
            "axis": axis,
            "case_id": case_id,
            "hold_only": True,
            "optimizer_eligible": False,
            "run_authorized": False,
            "split": "blind",
            "target": target,
            "target_hash": hashlib.sha256(target.encode()).hexdigest(),
            "training_authorized": False,
        })
        gold.append({"case_id": case_id, "axis": axis, "expected": expected, "observed": status, "reason": (observed.get("deterministic") or {}).get("reason")})
    PROMPTS.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in prompts), encoding="utf-8", newline="\n")
    GOLD.write_text(json.dumps({"schema_version": "mouth_semantics_blind_v3_gold", "rows": gold}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    report = {
        "schema_version": "mouth_semantics_blind_v3",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "BLIND_PASS" if not mismatches else "BLIND_FAIL",
        "rows": len(prompts),
        "matched": len(prompts) - len(mismatches),
        "mismatches": mismatches,
        "prompt_pack_sha256": sha(PROMPTS),
        "gold_sha256": sha(GOLD),
        "source_v2_preserved": True,
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("status", "rows", "matched", "mismatches", "optimizer_eligible", "training_authorized", "run_authorized")}, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
