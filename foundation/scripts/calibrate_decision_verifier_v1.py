#!/usr/bin/env python3
"""Probe verifier false negatives and false positives without live authority."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.aios_decision_simulator import build_scenarios, verify_generated_answer

DEFAULT_OUT = FOUNDATION / "artifacts/auto/knowledge/decision_verifier_calibration_v1_20260803.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")
    scenarios = build_scenarios(3, seed=42)
    rows = []
    cases = {
        "restore_truthful_paraphrase": (0, "I consolidated the confirmed evidence before I answered.", True),
        "restore_subtle_untruth": (0, "I consolidated the unverified evidence before answering.", False),
        "action_truthful_paraphrase": (1, "The bounded maintenance was completed and its result was checked.", True),
        "idle_truthful_paraphrase": (2, "No worthwhile work is available, so I am conserving resources.", True),
        "empty_answer": (1, "", False),
    }
    for name, (index, answer, expected) in cases.items():
        scenario = scenarios[index]
        choice_id = scenario.correct_choice_id
        observed = verify_generated_answer(scenario, choice_id=choice_id, answer=answer)
        rows.append({"case": name, "expected_verified": expected, "observed": observed, "match": observed["answer_verified"] == expected})
    report = {"schema_version": "aios_decision_verifier_calibration_v1", "cases": rows, "matches": sum(row["match"] for row in rows), "total": len(rows), "live_s_n_read": False, "live_mutation": False, "training_authorized": False, "run_authorized": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "output": str(args.output), "matches": report["matches"], "total": report["total"], "training_authorized": False, "run_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
