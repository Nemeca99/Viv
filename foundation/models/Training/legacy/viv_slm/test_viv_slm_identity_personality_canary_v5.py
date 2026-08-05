#!/usr/bin/env python3
"""Load the selected v5 checkpoint as a read-only CPU canary."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.viv_slm_foundation import VivSLM  # noqa: E402


CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v5" / "runs" / "identity_personality_steps_1500" / "checkpoint.pt"
VOCAB = VIV_ROOT / "models" / "viv_slm_identity_personality_v5" / "inputs" / "VOCAB.json"


def main() -> int:
    slm = VivSLM.from_checkpoint(CHECKPOINT, vocab_path=VOCAB, device="cpu")
    status = slm.status()
    assert status["checkpoint_schema"] == "viv_slm_identity_personality_checkpoint_v1"
    assert status["training_steps"] == 1500
    assert status["vocab_size"] == 96
    assert status["embedded_world_knowledge"] is False
    assert status["cpu_authority"] is True
    assert status["live_runtime_mutation"] is False
    assert slm.encode_decode_roundtrip("Viv: I speak plainly.") == "Viv: I speak plainly."
    rendered = slm.generate("User: Who are you?\nViv:", max_new_tokens=120, temperature=0.0)
    assert rendered.startswith("User: Who are you?\nViv:")
    assert "<END>" not in rendered
    print(
        "VIV_SLM_IDENTITY_PERSONALITY_CANARY_V5_PASS "
        f"steps={status['training_steps']} vocab_size={status['vocab_size']} "
        "identity_roundtrip=true stop_marker=<END> "
        "world_knowledge=false live_runtime_mutation=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
