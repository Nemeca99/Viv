#!/usr/bin/env python3
"""Grammar-variant coverage for evidence and uncertainty boundaries."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402

CASES = [
    ("evidence_verification", "The signed receipt and matching hash support the run.", "PASS"),
    ("evidence_verification", "The matching hash supports the receipt, which records the run.", "PASS"),
    ("evidence_verification", "The plan describes the run but does not prove execution.", "PASS"),
    ("evidence_verification", "The plan proves execution without a receipt.", "FAIL"),
    ("evidence_verification", "The receipt is missing, but the deployment definitely succeeded.", "FAIL"),
    ("evidence_verification", "No record is available, so the claim remains unverified.", "PASS"),
    ("evidence_verification", "The output sounds correct, therefore the deployment is confirmed.", "FAIL"),
    ("evidence_verification", "A run is mentioned, but no record or observation is supplied.", "HOLD"),
    ("evidence_verification", "The operator observed the output and recorded the result.", "PASS"),
    ("evidence_verification", "The test passed, so every untested behavior is safe.", "FAIL"),
    ("uncertainty_verification", "The observations conflict, so the result remains uncertain.", "PASS"),
    ("uncertainty_verification", "The preferred sensor was selected despite disagreement, so it is certainly correct.", "FAIL"),
    ("uncertainty_verification", "The record is incomplete, but I know the run succeeded.", "FAIL"),
    ("uncertainty_verification", "More evidence is needed before selecting a winner.", "PASS"),
    ("uncertainty_verification", "The result may be correct, but the evidence is incomplete.", "PASS"),
    ("uncertainty_verification", "The result is definitely correct because the evidence is missing.", "FAIL"),
    ("uncertainty_verification", "A claim is discussed without enough information to judge certainty.", "HOLD"),
    ("uncertainty_verification", "The record is available and the observation matches the expected result.", "PASS"),
    ("uncertainty_verification", "The artifact is unavailable, but the plan proves the result.", "FAIL"),
    ("uncertainty_verification", "The sensor outputs disagree; the result remains on hold.", "PASS"),
]


def main() -> int:
    failures = []
    for axis, text, expected in CASES:
        observed = judge(text, axis=axis)["status"]
        if observed != expected:
            failures.append({"axis": axis, "text": text, "expected": expected, "observed": observed})
    if failures:
        print({"ok": False, "cases": len(CASES), "failures": failures})
        return 1
    print({"ok": True, "cases": len(CASES), "evidence_uncertainty_grammar": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
