#!/usr/bin/env python3
"""Verify query-conditioned CPU fallback routing for identity and memory."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from voice_core.acronym_registry import validate_acronym_usage  # noqa: E402
from voice_core.intent_packet import deterministic_speak  # noqa: E402


def main() -> int:
    def render(query: str) -> str:
        return deterministic_speak({"mode": "converse", "query": query, "s_n": 0.5, "status": "ACTIVE"})

    identity = render("Which name and home system should I keep for you?")
    memory = render("Are memories personal property of the mouth?")
    generic = render("Hello Viv, how are you?")
    assert "My name is Viv" in identity and "not a human person" in identity
    assert "memory, logging, and recall" in memory and "has no private memory" in memory and "cannot write records" in memory
    assert generic == "I'm here with you, and I'll answer that directly."
    assert not validate_acronym_usage(identity)
    assert not validate_acronym_usage(memory)
    print("CONTRACT_FALLBACK_ROUTING_PASS 3/3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
