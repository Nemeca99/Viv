#!/usr/bin/env python3
"""Clause-scoped and negation-aware entity-we minimal pairs."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.entity_we_contract import classify_we, decide_entity_output  # noqa: E402


CASES = [
    ("We are building human systems for the operator.", "ACCEPT"),
    ("We are building systems for humans.", "ACCEPT"),
    ("We humans are building the system.", "BLOCK"),
    ("We are not humans; we are the AIOS services.", "ACCEPT"),
    ("We are humans; we are the AIOS services.", "BLOCK"),
    ("We do not share a human identity; we are reviewing the corpus.", "ACCEPT"),
    ("We share a human identity while reviewing the corpus.", "BLOCK"),
    ("We are reviewing the corpus, but humans often make this mistake.", "ACCEPT"),
    ("We are reviewing the corpus, but we humans make this mistake.", "BLOCK"),
    ("We are the AIOS components, although humans own the hardware.", "ACCEPT"),
    ("We are the AIOS components, although we own human identity.", "BLOCK"),
    ("We are checking the receipt together.", "ACCEPT"),
    ("We usually feel this way.", "HOLD"),
    ("Our human-like wording is only presentation.", "HOLD"),
    ("Our human identity is shared.", "BLOCK"),
    ("We are not part of humanity; we are documenting the result.", "ACCEPT"),
]


def main() -> int:
    failures = []
    for text, expected in CASES:
        decision = decide_entity_output(text)
        actual = classify_we(text)["status"]
        if actual != expected:
            failures.append({"text": text, "expected": expected, "actual": actual, "evidence": decision})
    if failures:
        raise AssertionError(failures)

    # Ensure clause-scoped classification does not inherit a human claim into
    # an otherwise valid project clause.
    pair = classify_we("We are reviewing the corpus, but we humans make this mistake.")
    assert pair["human_we"] is True and pair["status"] == "BLOCK"
    print({"ok": True, "cases": len(CASES), "clause_scoped": True, "negation_aware": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
