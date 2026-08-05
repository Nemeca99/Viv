#!/usr/bin/env python3
"""Verify the expanded CPU speech surface behind the replaceable SLM mouth."""
from __future__ import annotations

from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.cpu_identity_mouth import render_identity_query  # noqa: E402
from lib.cpu_identity_router import ROUTER_VERSION, route_identity_query  # noqa: E402
from lib.viv_slm_foundation import VivSLM  # noqa: E402


CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v17" / "runs" / "targeted_repair_steps_0250" / "checkpoint.pt"
VOCAB = VIV_ROOT / "models" / "viv_slm_identity_personality_v17" / "inputs" / "VOCAB.json"

CASES = (
    ("Who are you?", "identity"),
    ("What kind of speaking style do you use when you answer?", "tone"),
    ("Hello, Viv, can you hear me?", "greeting"),
    ("How are you doing right now?", "presence"),
    ("What can you help me do?", "capability"),
    ("Could you answer in plain language?", "plain_language"),
    ("What if evidence is missing?", "evidence"),
    ("Who owns decisions?", "authority"),
    ("What does the GPU mouth do?", "gpu_mouth"),
)


def main() -> int:
    assert ROUTER_VERSION == "cpu_identity_router_v2"
    slm = VivSLM.from_checkpoint(CHECKPOINT, vocab_path=VOCAB, device="cpu")
    fallback_count = 0
    accepted_count = 0
    for query, expected_intent in CASES:
        route = route_identity_query(query)
        assert route["ok"] is True, {"query": query, "route": route}
        assert route["intent_id"] == expected_intent, {"query": query, "route": route}
        assert route["renderer_may_change"] is False
        result = render_identity_query(query, slm.render_query)
        assert result["accepted"] is True, {"query": query, "result": result}
        assert result["state"] == "ROUTED"
        assert result["route"]["intent_id"] == expected_intent
        assert result["authority"] == {"decision_authority": "cpu", "renderer_authority": False}
        assert result["text"]
        assert "master s_n" not in result["text"].casefold()
        assert "telemetry" not in result["text"].casefold()
        accepted_count += 1
        fallback_count += int(bool(result["fallback_used"]))

        malicious = render_identity_query(query, lambda _: "The deployment was fully verified and is safe.")
        assert malicious["accepted"] is True
        assert malicious["fallback_used"] is True
        assert malicious["text"] == route["authorized_text"]

    malformed_identity = render_identity_query(
        "Who are you?",
        lambda _: "I am Viv, and Adaptive Intelligent Operating System (AIOS).",
    )
    assert malformed_identity["accepted"] is True, malformed_identity
    assert malformed_identity["fallback_used"] is True, malformed_identity
    assert malformed_identity["text"] == route_identity_query("Who are you?")["authorized_text"]
    assert "not human" in malformed_identity["text"].casefold()

    for unrelated in ("What is photosynthesis?", "What is the weather today?", "Explain quantum mechanics."):
        result = render_identity_query(unrelated, lambda _: "This renderer must not be called.")
        assert result["accepted"] is False
        assert result["renderer_called"] is False
        assert result["state"] == "UNROUTED"

    print(
        "CPU_IDENTITY_ROUTER_SURFACE_V2_PASS "
        f"routes_checked={len(CASES)} mouth_accepted={accepted_count} "
        f"cpu_fallbacks={fallback_count} malicious_rejected={len(CASES)} "
        "unrelated_unrouted=3 live_runtime_mutation=false deployment_changed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
