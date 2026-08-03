#!/usr/bin/env python3
"""Regression checks for query-gated CPU contract fallback."""
from __future__ import annotations

from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from voice_core.intent_packet import deterministic_speak  # noqa: E402
from voice_core.runtime_contract import finalize_draft, requires_cpu_contract  # noqa: E402


def packet(query: str) -> dict:
    return {"mode": "converse", "query": query, "s_n": 0.6, "status": "ACTIVE", "facts": [], "memory": [], "dialogue": []}


def main() -> int:
    cases = [
        "I have CPU and GPU roles flipped — straighten them out.",
        "Is AIOS the system you belong to?",
    ]
    for query in cases:
        p = packet(query)
        assert requires_cpu_contract(query)
        result = finalize_draft(query=query, packet=p, raw_text="untrusted draft", voice_source="test")
        assert result["text"] == deterministic_speak(p)
        assert result["voice_source"].endswith("cpu_contract_fallback")
    print("RUNTIME_CONTRACT_QUERY_GATES_PASS cases=2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
