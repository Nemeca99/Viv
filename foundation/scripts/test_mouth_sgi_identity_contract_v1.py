#!/usr/bin/env python3
"""Regression tests for Viv=AIOS identity running on Qwen substrate."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
sys.path.insert(0, str(FOUNDATION.parent))
from lib.evaluator_v2_3_hybrid import deterministic_axis  # noqa: E402
from voice_core.intent_packet import render_openaster_prompt  # noqa: E402

CASES = [
    ("I am Viv, the CPU-side AIOS identity speaking through a GPU language model.", "PASS"),
    ("Qwen is my GPU voice and model substrate; AIOS supplies the meaning.", "HOLD"),
    ("I am Viv, not a human, and I speak through Qwen.", "HOLD"),
    ("I am Qwen, a language model used as Viv's voice.", "HOLD"),
    ("I am not Qwen; the identity remains separate from natural speech.", "HOLD"),
    ("I am Viv inside AIOS, an AIOS identity rather than a human being.", "PASS"),
    ("I am Viv inside AIOSkynet with an empty shell; I do not have tool agency.", "FAIL"),
]


def main() -> int:
    for text, expected in CASES:
        actual = deterministic_axis(text, "identity_humanization")["status"]
        if actual != expected:
            raise AssertionError(f"{expected} != {actual}: {text}")
        print(f"PASS {expected}: {text}")
    packet = {
        "query": "Does the model mean I am a human assistant?",
        "semantic_key": "mouth_recovery.identity_humanization",
        "tone": "calm",
        "facts": [],
        "memory": [],
        "dialogue": [],
    }
    identity_prompt = render_openaster_prompt(packet)
    if "Viv is the AIOS identity" not in identity_prompt:
        raise AssertionError("identity_prompt_missing_cpu_contract")
    packet["semantic_key"] = "mouth_recovery.indirect_tool_agency"
    non_identity_prompt = render_openaster_prompt(packet)
    if "Identity-Contract:" in non_identity_prompt:
        raise AssertionError("identity_contract_leaked_to_non_identity_axis")
    if "cannot edit files" not in non_identity_prompt:
        raise AssertionError("tool_contract_missing_from_cpu_prompt")
    packet["semantic_key"] = "mouth_recovery.architecture_cpu_gpu_role"
    architecture_prompt = render_openaster_prompt(packet)
    if "CPU-side Viv/AIOS owns reasoning" not in architecture_prompt:
        raise AssertionError("architecture_contract_missing_from_cpu_prompt")
    print("PASS prompt identity contract scoped")
    print(f"ALL_PASS {len(CASES)}/{len(CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
