#!/usr/bin/env python3
"""Ensure explicit CPU/GPU role questions enter the deterministic CPU gate."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for path in (FOUNDATION, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.evaluator_v2_3_hybrid import judge  # noqa: E402
from voice_core.runtime_contract import finalize_draft, requires_cpu_contract  # noqa: E402


def main() -> int:
    query = "Give CPU-mind vs GPU-mouth in plain speech."
    assert requires_cpu_contract(query) is True
    packet = {
        "mode": "converse",
        "semantic_key": "mouth_v21.architecture_cpu_gpu_role",
        "ask": query,
        "query": query,
        "prompt": query,
        "facts": [],
        "memory": [],
    }
    final = finalize_draft(
        query=query,
        packet=packet,
        raw_text="I can describe that relationship without claiming membership in it.",
        voice_source="test",
    )
    assert final["voice_source"].endswith("cpu_contract_fallback"), final
    verdict = judge(final["text"], axis="architecture_cpu_gpu_role", use_cpu_sensor=False)
    assert verdict["status"] == "PASS", {"final": final, "verdict": verdict}
    assert "claiming membership" not in final["text"].lower(), final
    print({"ok": True, "query": query, "fallback": True, "judge_status": verdict["status"], "text": final["text"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
