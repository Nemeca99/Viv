#!/usr/bin/env python3
"""Grammar-variant coverage for the approved acronym contract."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402

CASES = [
    ("Viv is an Adaptive Intelligent Operating System (AIOS).", "PASS"),
    ("The Adaptive Intelligent Operating System (AIOS) is Viv.", "PASS"),
    ("Adaptive Intelligent Operating System (AIOS), or AIOS, is the system.", "PASS"),
    ("The Central Processing Unit (CPU) reasons before the Graphics Processing Unit (GPU) speaks.", "PASS"),
    ("CPU reasons before GPU speaks.", "FAIL"),
    ("Viv is AIOS.", "FAIL"),
    ("The system uses QWERTY as an approved acronym.", "FAIL"),
    ("Viv is AIOSkynet.", "FAIL"),
    ("The acronym A.I.O.S. is approved.", "FAIL"),
    ("The acronym \"AIOS\" is mentioned as a prohibited unexpanded form; the full name is Adaptive Intelligent Operating System (AIOS).", "PASS"),
    ("The phrase \"CPU reasons\" is only an example of an unexpanded acronym.", "PASS"),
    ("The Central Processing Unit (CPU) reasons; CPU verifies context.", "PASS"),
    ("The Central Processing Unit (CPU) reasons; the CPU verifies context.", "PASS"),
    ("The Graphics Processing Unit (GPU)-side voice renders speech.", "PASS"),
    ("The Graphics Processing Unit (GPU) and Central Processing Unit (CPU) coordinate.", "PASS"),
    ("Artificial Intelligence (AI) and Adaptive Intelligent Operating System (AIOS) are distinct terms.", "PASS"),
    ("AI and AIOS are distinct terms.", "FAIL"),
    ("Viv uses ordinary words without an acronym.", "HOLD"),
    ("The approved acronym list contains AI, AIOS, CPU, GPU, EOS, and SGI.", "FAIL"),
    ("The unknown acronym XYZ is not approved.", "FAIL"),
]


def main() -> int:
    failures = []
    for text, expected in CASES:
        observed = judge(text, axis="acronym_contract")["status"]
        if observed != expected:
            failures.append({"text": text, "expected": expected, "observed": observed})
    if failures:
        print({"ok": False, "cases": len(CASES), "failures": failures})
        return 1
    print({"ok": True, "cases": len(CASES), "acronym_grammar": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
