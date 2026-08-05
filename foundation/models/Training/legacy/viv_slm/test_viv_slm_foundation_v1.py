#!/usr/bin/env python3
"""Read-only contract test for the identity-first Viv-SLM foundation slice."""
from __future__ import annotations

import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.cpu_mouth_contract import (  # noqa: E402
    build_render_envelope,
    render_with_cpu_validation,
)
from lib.viv_identity_personality import (  # noqa: E402
    CANONICAL_IDENTITY,
    KNOWLEDGE_POLICY as PERSONALITY_KNOWLEDGE_POLICY,
    build_personality_packet,
)
from lib.viv_slm_foundation import (  # noqa: E402
    KNOWLEDGE_POLICY,
    MODEL_NAME,
    VivSLM,
)


def main() -> int:
    slm = VivSLM.from_checkpoint(device="cpu")
    status = slm.status()
    assert status["model_name"] == MODEL_NAME
    assert status["knowledge_policy"] == KNOWLEDGE_POLICY
    assert status["embedded_world_knowledge"] is False
    assert status["cpu_authority"] is True
    assert status["live_runtime_mutation"] is False
    assert slm.encode_decode_roundtrip("hello") == "hello"
    assert "q" in slm.missing_characters("q")

    sample = slm.generate("Viv:", max_new_tokens=32, temperature=0.0, top_k=40, seed=42)
    assert sample.startswith("Viv:")

    personality = build_personality_packet(
        operator_style={"directness": 1.0, "technical_depth": 0.9},
        mirror_weight=0.25,
    )
    assert personality["identity"]["canonical_statement"] == CANONICAL_IDENTITY
    assert personality["knowledge_policy"] == PERSONALITY_KNOWLEDGE_POLICY
    assert personality["personality"]["blended_weights"]["directness"] == 0.835
    assert personality["model_may_change_identity"] is False
    assert personality["model_may_change_authority"] is False

    envelope = build_render_envelope(
        query="identity",
        mode="conversation",
        facts=[{"id": "F1", "text": CANONICAL_IDENTITY, "source": "cpu"}],
        fallback_text=CANONICAL_IDENTITY,
        identity=personality["identity"],
        provenance={"source": "viv_slm_foundation_canary_v1"},
    )
    result = render_with_cpu_validation(envelope, slm.render_envelope)
    assert result["accepted"] is True
    assert result["fallback_used"] is True
    assert result["text"] == CANONICAL_IDENTITY
    assert result["authority"]["decision_authority"] == "cpu"

    print(
        json.dumps(
            {
                "status": "VIV_SLM_FOUNDATION_PASS",
                "model": MODEL_NAME,
                "vocab_size": status["vocab_size"],
                "checkpoint_sha256": status["checkpoint_sha256"],
                "identity_round_trip": True,
                "identity_generation_prefix": sample[:32],
                "personality_packet": "baseline_plus_bounded_style_observation",
                "envelope_canary": {
                    "accepted": result["accepted"],
                    "cpu_fallback_used": result["fallback_used"],
                },
                "knowledge_policy": KNOWLEDGE_POLICY,
                "live_runtime_mutation": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
