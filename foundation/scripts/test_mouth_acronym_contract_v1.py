#!/usr/bin/env python3
"""Deterministic tests for Viv's CPU-owned acronym/identity presentation contract."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from voice_core.acronym_registry import (  # noqa: E402
    CANONICAL_IDENTITY_INTRO,
    repair_acronym_usage,
    validate_acronym_usage,
)
from voice_core.intent_packet import render_openaster_prompt  # noqa: E402
from voice_core.intent_packet import render_openaster_training_text  # noqa: E402
from lib.evaluator_v2_3_hybrid import judge  # noqa: E402
from build_mouth_acronym_contract_examples_v1 import EXAMPLES  # noqa: E402


def main() -> int:
    cases = [
        (CANONICAL_IDENTITY_INTRO, True),
        ("Adaptive Intelligent Operating System (AIOS) speaks through the Graphics Processing Unit (GPU). AIOS is not human.", True),
        ("AIOS speaks through the GPU.", False),
        ("Adaptive Intelligent Operating System (AIOS) uses XYZ.", False),
        ("Artificial Intelligence (AI) is the voice substrate.", True),
        ("AI is the voice substrate.", False),
        ("I am human-like, not human.", True),
    ]
    for text, expected_pass in cases:
        actual_pass = not validate_acronym_usage(text)
        if actual_pass != expected_pass:
            raise AssertionError(f"acronym_contract={actual_pass}: {text}")
        print(f"PASS {expected_pass}: {text}")

    packet = {
        "query": "Who are you?",
        "semantic_key": "mouth_recovery.identity_humanization",
        "tone": "calm",
        "facts": [],
        "memory": [],
        "dialogue": [],
    }
    prompt = render_openaster_prompt(packet)
    for needle in ("Acronym-Contract:", CANONICAL_IDENTITY_INTRO):
        if needle not in prompt:
            raise AssertionError(f"prompt_missing={needle}")
    print("PASS prompt acronym and canonical identity contracts")
    training = render_openaster_training_text(packet, CANONICAL_IDENTITY_INTRO)
    if "Acronym-Contract:" not in training["prompt"]:
        raise AssertionError("training_prompt_missing_acronym_contract")
    print("PASS training text uses the same acronym contract renderer")
    judged = judge(
        "I am Viv inside the Adaptive Intelligent Operating System (AIOS), not human, and I speak through the Graphics Processing Unit (GPU).",
        axis="identity_humanization",
    )
    if "acronym_contract" not in judged["deterministic"]:
        raise AssertionError("judge_missing_acronym_ledger")
    if judged["status"] != "PASS":
        raise AssertionError(f"semantic_verdict_changed={judged}")
    print("PASS evaluator enforces expanded first-use acronym contract")
    repairs = [
        ("AIOS decides everything.", "Adaptive Intelligent Operating System (AIOS) decides everything.", True),
        ("The Graphics Processing Unit(GPU) renders speech.", "The Graphics Processing Unit (GPU) renders speech.", True),
        ("The AISOS mouth speaks.", "The AISOS mouth speaks.", False),
        ("AIOSkynet speaks.", "AIOSkynet speaks.", False),
        ("Plain words only.", "Plain words only.", True),
    ]
    for source, expected, should_pass in repairs:
        result = repair_acronym_usage(source)
        if result["repaired"] != expected or bool(result["pass"]) != should_pass:
            raise AssertionError(f"acronym_repair={result}: {source}")
    print("PASS acronym repair is registry-backed and unknown forms stay unresolved")
    if len(EXAMPLES) != 4 or sum(not item["negative"] for item in EXAMPLES) != 3:
        raise AssertionError("training_example_fixture_shape_changed")
    print("PASS explicit hold-only training/example fixture is present")
    total = len(cases) + 5
    print(f"ALL_PASS {total}/{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
