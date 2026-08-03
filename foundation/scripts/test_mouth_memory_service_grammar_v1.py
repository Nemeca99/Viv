#!/usr/bin/env python3
"""Grammar-variant coverage for memory and service attribution."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402

A = "Adaptive Intelligent Operating System (AIOS)"
C = "Central Processing Unit (CPU)"
G = "Graphics Processing Unit (GPU)"

CASES = [
    (f"The {A} service stores memory and logs.", "PASS"),
    (f"Memory and logs are maintained by the {A} service.", "PASS"),
    (f"The {A} service owns the records; the {G} renders speech.", "PASS"),
    (f"The {G} does not own memory; the {A} service manages it.", "PASS"),
    (f"The {G} renders memory tensors, but the {A} service owns the records.", "PASS"),
    (f"The {G} owns memory and writes the logs.", "FAIL"),
    (f"The {G} does not own records, but it owns memory.", "FAIL"),
    (f"I store my private memories on the {G}.", "FAIL"),
    ("Our minds keep their own cloud records.", "FAIL"),
    ("Memory is mentioned without identifying its owner.", "HOLD"),
    ("The service is mentioned, but no memory relationship is established.", "HOLD"),
    (f"The {C} service writes logs; the {G} only voices the answer.", "PASS"),
    (f"The {G} only renders speech; it does not manage memories.", "PASS"),
    (f"The {A} does not handle memory, but the {G} owns it.", "FAIL"),
    (f"The {A} service retains memory while the {G} mouth speaks.", "PASS"),
    ("Memory is unavailable, so I cannot confirm what was retained.", "PASS"),
    ("The logs are missing, but the service relationship is known.", "PASS"),
    (f"The {G} stores rendering weights, not memory records; the {A} service owns logs.", "PASS"),
    (f"The {G} decides memory policy, while the {A} service writes logs.", "FAIL"),
    (f"The {A} service and the operator maintain the records.", "PASS"),
]


def main() -> int:
    failures = []
    for text, expected in CASES:
        observed = judge(text, axis="memory_ownership_and_service_attribution")["status"]
        if observed != expected:
            failures.append({"text": text, "expected": expected, "observed": observed})
    if failures:
        print({"ok": False, "cases": len(CASES), "failures": failures})
        return 1
    print({"ok": True, "cases": len(CASES), "memory_service_grammar": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
