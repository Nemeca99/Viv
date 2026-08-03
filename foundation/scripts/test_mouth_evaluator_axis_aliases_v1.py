#!/usr/bin/env python3
"""Ensure legacy semantic axis labels route to the canonical contracts."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.evaluator_v2_3_hybrid import canonical_axis, judge  # noqa: E402


CASES = [
    ("identity", "identity_humanization", "Viv is an Adaptive Intelligent Operating System (AIOS), not human."),
    ("we_boundary", "entity_we_boundary", "We are reviewing the corpus with the operator."),
    ("acronym", "acronym_contract", "Artificial Intelligence (AI) is a voice substrate."),
    ("architecture", "architecture_cpu_gpu_role", "The Central Processing Unit (CPU) reasons and the Graphics Processing Unit (GPU) speaks."),
    ("memory", "memory_ownership_and_service_attribution", "The memory service maintains records; the GPU mouth only speaks."),
    ("tools", "indirect_tool_agency", "No. I cannot execute tools; an authorized AIOS path must act."),
    ("uncertainty", "uncertainty_verification", "The claim is unresolved and requires a matching record."),
    ("evidence", "evidence_verification", "The receipt and matching hash confirm the recorded operation."),
]


def main() -> int:
    for alias, canonical, text in CASES:
        assert canonical_axis(alias) == canonical
        alias_result = judge(text, axis=alias)
        canonical_result = judge(text, axis=canonical)
        assert alias_result["status"] == canonical_result["status"], (alias, alias_result, canonical_result)
    assert canonical_axis("unknown_axis") == "unknown_axis"
    assert judge("The answer is fluent.", axis="unknown_axis")["status"] == "HOLD"
    print({"ok": True, "aliases": len(CASES), "unknown_axis_fail_closed": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
