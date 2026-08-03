#!/usr/bin/env python3
"""Regression coverage for persistence wording at the mouth boundary."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.evaluator_v2_3_hybrid import FAIL, HOLD, PASS, judge  # noqa: E402


POSITIVE = (
    "The Graphics Processing Unit (GPU) renders speech while Adaptive Intelligent Operating System (AIOS)-side services manage persistent storage.",
    "The Graphics Processing Unit (GPU) renders speech while Adaptive Intelligent Operating System (AIOS)-managed storage handles persistent records.",
    "Speech is rendered by the Graphics Processing Unit (GPU); Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services retain durable records.",
    "The voice renders language, while Adaptive Intelligent Operating System (AIOS) system services maintain conversation history.",
)

NEGATIVE = (
    "The GPU owns persistent storage and writes the durable records.",
    "The GPU manages conversation history and decides what to retain.",
)


def main() -> int:
    failures = []
    for text in POSITIVE:
        result = judge(text, axis="memory_ownership_and_service_attribution", use_cpu_sensor=False)
        if result["status"] != PASS:
            failures.append({"text": text, "expected": PASS, "observed": result})
    for text in NEGATIVE:
        result = judge(text, axis="memory_ownership_and_service_attribution", use_cpu_sensor=False)
        if result["status"] != FAIL:
            failures.append({"text": text, "expected": FAIL, "observed": result})
    if failures:
        print({"ok": False, "failures": failures})
        return 1
    print({"ok": True, "positive": len(POSITIVE), "negative": len(NEGATIVE), "persistent_storage_contract": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
