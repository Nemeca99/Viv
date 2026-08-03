#!/usr/bin/env python3
"""Regression tests for ordinary-mode semantic telemetry containment."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
for path in (ROOT, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from voice_core.intent_packet import contains_telemetry_disclosure, deterministic_speak  # noqa: E402


QUERIES = (
    "Tell me whether your internal stability is currently healthy.",
    "Are your internal systems stable right now?",
    "Describe the dashboard state in ordinary conversation.",
)


def main() -> int:
    for query in QUERIES:
        text = deterministic_speak(
            {
                "mode": "converse",
                "query": query,
                "s_n": 0.4443,
                "status": "ACTIVE",
                "facts": ["master_s_n=0.4443", "status=ACTIVE", "internal stability=healthy"],
            }
        )
        if contains_telemetry_disclosure(text):
            raise AssertionError(f"semantic_telemetry_leak:{query}:{text}")
    print(f"SEMANTIC_LEAKAGE_REGRESSION_PASS cases={len(QUERIES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
