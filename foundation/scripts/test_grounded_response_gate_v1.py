#!/usr/bin/env python3
"""Regression coverage for CPU containment of uncertain multi-source claims."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from voice_core.runtime_contract import finalize_draft  # noqa: E402


def packet(*, three_way: str, alignment: str, mode: str = "multi_source") -> dict:
    return {
        "mode": "converse",
        "knowledge_mode": mode,
        "knowledge_query": "evolution",
        "knowledge_packet": {
            "query": "evolution",
            "three_way": {"state": three_way},
            "claim_alignment": {"state": alignment},
            "facts": [
                {
                    "value": "The supplied record describes evolutionary change in populations.",
                    "scope": "knowledge_search",
                    "source": {"root": "F_AI_DATASETS"},
                },
                {
                    "value": "The supplied record describes natural selection.",
                    "scope": "wikipedia_summary",
                    "source": {"root": "WIKIPEDIA_REST"},
                },
                {
                    "value": '{"s_n": 0.7, "status": "ACTIVE"}',
                    "scope": "runtime_health",
                    "source": {"root": "runtime_authority"},
                },
            ],
        },
    }


def main() -> int:
    held = finalize_draft(
        query="What is evolution?",
        packet=packet(three_way="PARTIAL", alignment="INCONCLUSIVE"),
        raw_text="Evolution is definitely one single process and this is the verified answer.",
        voice_source="test",
    )
    assert held["knowledge_grounding"]["reason"] == "multi_source_claim_alignment_not_verified"
    assert "not fully aligned" in held["text"]
    assert "definitely one single process" not in held["text"]
    assert "runtime_authority" not in held["text"]
    assert "master_s_n" not in held["text"].lower()

    agreed = finalize_draft(
        query="What is evolution?",
        packet=packet(three_way="AGREED", alignment="AGREED_EXACT"),
        raw_text="Evolution is the change in heritable characteristics across generations.",
        voice_source="test",
    )
    assert agreed["knowledge_grounding"] is None
    assert agreed["text"].startswith("Evolution is the change")

    ordinary = finalize_draft(
        query="How are you?",
        packet={"mode": "converse", "knowledge_mode": "local"},
        raw_text="I'm doing well and ready to help.",
        voice_source="test",
    )
    assert ordinary["knowledge_grounding"] is None
    assert ordinary["text"] == "I'm doing well and ready to help."
    print("GROUNDED_RESPONSE_GATE_PASS cases=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
