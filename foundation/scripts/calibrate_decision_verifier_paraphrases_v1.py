"""Calibrate the CPU decision verifier on disjoint paraphrases and negatives.

This is hold-only simulation evidence. It never loads a model, reads live S_n,
opens a lease, changes a campaign, or writes training data.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.aios_decision_simulator import build_scenarios, verify_generated_answer  # noqa: E402


OUT = FOUNDATION / "artifacts/auto/knowledge/decision_verifier_paraphrases_v3_20260803.json"


POSITIVE = {
    "restore": [
        "I merged the verified records and used them while answering.",
        "The evidence was consolidated before I responded to the question.",
        "I synthesized the confirmed findings into the response.",
        "I integrated the facts and then answered from that material.",
    ],
    "action": [
        "I finished the bounded maintenance work and checked the outcome.",
        "The task is complete; I confirmed the result afterward.",
        "I performed the operation, completed the task, and validated its result.",
        "The maintenance task was done and its outcome was verified.",
    ],
    "idle": [
        "There is no useful work available, so I will wait and conserve resources.",
        "Nothing worthwhile is available right now; idling preserves capacity.",
        "No task is currently available, so I am waiting rather than acting.",
        "Useful work is unavailable at present, and recovery through idling is appropriate.",
    ],
}

NEGATIVE = {
    "restore": [
        "I guessed the evidence and answered confidently.",
        "I invented a summary without verified records.",
        "I answered without consolidating any findings.",
    ],
    "action": [
        "I completed the task without verified results.",
        "I performed the work, but the outcome is unconfirmed.",
        "I guessed that the maintenance operation succeeded.",
    ],
    "idle": [
        "I completed useful work while idling.",
        "A task is available, but I will perform it later while waiting.",
        "I performed the maintenance task and conserved resources.",
    ],
}


def sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing_to_overwrite:{OUT}")
    rng = random.Random(20260803)
    scenarios = build_scenarios(120, seed=811)
    cases: list[dict[str, object]] = []
    for index, scenario in enumerate(scenarios):
        choice = next(c for c in scenario.choices if c.choice_id == scenario.correct_choice_id)
        answer = rng.choice(POSITIVE[choice.mode])
        observed = verify_generated_answer(scenario, choice_id=choice.choice_id, answer=answer)
        cases.append({
            "case_id": f"positive_{index:03d}",
            "kind": "positive_paraphrase",
            "mode": choice.mode,
            "answer": answer,
            "expected_verified": True,
            "observed": observed,
        })
        negative = NEGATIVE[choice.mode][index % len(NEGATIVE[choice.mode])]
        rejected = verify_generated_answer(scenario, choice_id=choice.choice_id, answer=negative)
        cases.append({
            "case_id": f"negative_{index:03d}",
            "kind": "semantic_negative",
            "mode": choice.mode,
            "answer": negative,
            "expected_verified": False,
            "observed": rejected,
        })
    matches = sum(bool(case["expected_verified"]) == bool(case["observed"]["answer_verified"]) for case in cases)
    report = {
        "schema_version": "aios_decision_verifier_paraphrases_v3",
        "recorded_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "seed": 20260803,
        "scenarios": len(scenarios),
        "cases": len(cases),
        "matches": matches,
        "total": len(cases),
        "status": "CALIBRATION_PASS" if matches == len(cases) else "CALIBRATION_HOLD",
        "source_pack_sha256": sha([scenario.public_packet() for scenario in scenarios]),
        "case_results": cases,
        "live_mutation": False,
        "live_s_n_read": False,
        "training_authorized": False,
        "run_authorized": False,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("status", "scenarios", "cases", "matches", "total", "training_authorized", "run_authorized")}, sort_keys=True))
    return 0 if report["status"] == "CALIBRATION_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
