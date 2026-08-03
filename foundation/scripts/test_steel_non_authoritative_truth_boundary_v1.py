#!/usr/bin/env python3
"""Prove the absorbed steel heuristic is not a factual truth gate."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from lib.steel_judge import evaluate  # noqa: E402
from voice_core.runtime_contract import finalize_draft  # noqa: E402


def main() -> int:
    # Deliberately fail the stability heuristic: unrelated previous text,
    # low S_n. This says nothing about factual support.
    steel = evaluate(
        "The supplied record describes natural selection.",
        "unrelated prior draft",
        master_s_n=0.20,
    )
    assert steel["passed"] is False

    packet = {
        "mode": "converse",
        "knowledge_mode": "multi_source",
        "knowledge_query": "evolution",
        "knowledge_packet": {
            "query": "evolution",
            "three_way": {"state": "AGREED"},
            "claim_alignment": {"state": "AGREED_EXACT"},
            "facts": [
                {
                    "value": "The supplied record describes natural selection.",
                    "scope": "knowledge_search",
                    "source": {"root": "F_AI_DATASETS"},
                },
                {
                    "value": "The supplied record describes natural selection.",
                    "scope": "wikipedia_summary",
                    "source": {"root": "WIKIPEDIA_REST"},
                },
            ],
        },
    }
    finalized = finalize_draft(
        query="What is evolution?",
        packet=packet,
        raw_text="The supplied record describes natural selection.",
        voice_source="boundary_test",
    )
    assert finalized["text"] == "The supplied record describes natural selection."
    assert finalized["knowledge_grounding"] is None
    print("STEEL_NON_AUTHORITATIVE_TRUTH_BOUNDARY_PASS steel_rejected_answer_preserved=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
