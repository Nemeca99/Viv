#!/usr/bin/env python3
"""Regression cases for semantic UML/standard rendering equivalence."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.uml_engine import evaluate, verify  # noqa: E402


CASES = (
    ("[3,4]", 7.0),
    ("{10,3}", 7.0),
    (">6,7<", 42.0),
    ("<{8,2},3>", 2.0),
    ("^3[2]", 8.0),
    ("![5]", 120.0),
    ("%[17,5]", 2.0),
    ("[pi,pi]", 6.283185307179586),
    ("&[2,8]", 3.0),
    ("|~[5]", 5.0),
    ("\\/[9]", 3j),
)


def main() -> int:
    failures = []
    for expr, expected in CASES:
        try:
            value, _node, _notation, _trace = evaluate(expr)
            ok, report = verify(expr)
            if not ok or abs(complex(value) - complex(expected)) > 1e-9:
                failures.append((expr, value, expected, report))
        except Exception as exc:  # noqa: BLE001 — regression should report the case
            failures.append((expr, type(exc).__name__, expected, str(exc)))
    if failures:
        print("FAIL uml_engine_verify_equivalence")
        for row in failures:
            print(row)
        return 1
    print(f"PASS uml_engine_verify_equivalence cases={len(CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
