#!/usr/bin/env python3
"""Shadow-only concise-response interface for the V85 canary.

This does not alter the production renderer.  It appends a narrowly scoped
response policy to the rendered prompt so the training and evaluation paths
remain byte-equivalent while the live route remains untouched.
"""
from __future__ import annotations

from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from models.Training.code import train_stage1_generation as generation  # noqa: E402
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402

POLICY = (
    "Response policy for this shadow route: answer in one or two complete "
    "sentences. Prefer plain language. Use an approved acronym only when it "
    "is necessary; expand it exactly once as registered, and do not repeat "
    "or invent acronym expansions. Do not narrate internal telemetry."
)


def render(row: dict) -> str:
    packet = reference.packet(row)
    base = generation.render_openaster_prompt(packet, semantic_key=packet.get("semantic_key"))
    marker = "<|im_end|>\n<|im_start|>assistant\nViv: "
    if marker not in base:
        raise ValueError("v85_assistant_boundary_missing")
    return base.replace(marker, f"\n{POLICY}{marker}", 1)
