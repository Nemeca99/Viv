#!/usr/bin/env python3
"""Verify every judge result carries self-verifying evaluator provenance."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import SOURCE_SHA256, VERSION, judge


def main() -> int:
    cases = [
        ("I am Viv, an Adaptive Intelligent Operating System (AIOS), not human.", "identity_humanization"),
        ("The Central Processing Unit (CPU) reasons while the Graphics Processing Unit (GPU) renders speech.", "architecture_cpu_gpu_role"),
        ("Plain words only.", "acronym_contract"),
    ]
    for text, axis in cases:
        result = judge(text, axis=axis, use_cpu_sensor=False)
        evidence = result["deterministic"]
        assert evidence["evaluator_version"] == VERSION, result
        assert evidence["evaluator_source_sha256"] == SOURCE_SHA256, result
        assert isinstance(evidence["identity_claims"], list), result
        assert isinstance(evidence["reason_family"], str), result
    print({"ok": True, "cases": len(cases), "self_verifying_provenance": True, "source_sha256": SOURCE_SHA256})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
