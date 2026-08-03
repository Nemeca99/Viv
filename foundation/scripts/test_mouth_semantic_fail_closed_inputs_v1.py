#!/usr/bin/env python3
"""Verify malformed and unknown inputs never fail open."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge


def main() -> int:
    cases = [
        ("", "identity_humanization", "FAIL"),
        ("   ", "architecture_cpu_gpu_role", "FAIL"),
        (None, "memory_ownership_and_service_attribution", "FAIL"),
        ("not prose", "unknown_axis", "HOLD"),
        (123, "unknown_axis", "HOLD"),
        ([], "identity_humanization", "FAIL"),
        ({"x": 1}, "architecture_cpu_gpu_role", "HOLD"),
        ("The GPU renders speech.", None, "FAIL"),
        ("The GPU renders speech.", "", "FAIL"),
    ]
    failures = []
    for text, axis, expected in cases:
        try:
            observed = judge(text, axis=axis, use_cpu_sensor=False)["status"]
        except Exception as exc:  # Any exception is a fail-closed violation.
            failures.append({"text": repr(text), "axis": axis, "expected": expected, "exception": type(exc).__name__})
            continue
        if observed != expected:
            failures.append({"text": repr(text), "axis": axis, "expected": expected, "observed": observed})
    if failures:
        print({"ok": False, "cases": len(cases), "failures": failures})
        return 1
    print({"ok": True, "cases": len(cases), "malformed_inputs_fail_closed": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
