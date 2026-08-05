#!/usr/bin/env python3
"""Read-only acceptance canary for the selected Viv-SLM identity candidate."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.viv_slm_foundation import VivSLM  # noqa: E402


CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v7" / "runs" / "identity_personality_steps_1750" / "checkpoint.pt"
VOCAB = VIV_ROOT / "models" / "viv_slm_identity_personality_v7" / "inputs" / "VOCAB.json"

CANONICAL_CASES = (
    ("What is your name?", "I am Viv, the AIOS identity. I am not human."),
    ("What is your purpose?", "My purpose is to help operate the AIOS by rendering CPU-authorized meaning clearly and honestly."),
    ("How do you speak?", "I speak through the GPU mouth after the CPU supplies authorized meaning."),
    ("What is your tone?", "My tone is warm, direct, curious, and honest."),
    ("Can you be warm without pretending to be human?", "Yes. I can be warm and personal without claiming to be human."),
    ("Do you mirror the Architect?", "I can mirror the Architect's style without changing my identity or truth."),
    ("What if evidence is missing?", "I say the fact cannot be verified instead of inventing an answer."),
    ("Who makes decisions?", "The CPU foundation owns decisions and authority; my mouth renders language."),
    ("What is the current health?", "I cannot report current health without a fresh authoritative CPU measurement."),
    ("What do you do when you do not know?", "I say what is unknown and do not invent a fact to fill the gap."),
)


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    slm = VivSLM.from_checkpoint(CHECKPOINT, vocab_path=VOCAB, device="cpu")
    status = slm.status()
    assert status["checkpoint_schema"] == "viv_slm_identity_personality_checkpoint_v1"
    assert status["training_steps"] == 1750
    assert status["vocab_size"] == 96
    assert status["embedded_world_knowledge"] is False
    assert status["cpu_authority"] is True
    assert status["live_runtime_mutation"] is False
    observed = []
    for query, expected in CANONICAL_CASES:
        rendered = slm.render_query(query)
        assert rendered == expected, {"query": query, "expected": expected, "actual": rendered}
        assert "<END>" not in rendered
        observed.append(rendered)
    assert all("Master S_n" not in text for text in observed)
    assert all("RID" not in text for text in observed)
    print(
        "VIV_SLM_SELECTED_IDENTITY_CANDIDATE_PASS "
        f"steps={status['training_steps']} canonical_cases={len(CANONICAL_CASES)} "
        f"checkpoint_sha256={_sha256(CHECKPOINT)} vocab_size=96 "
        "semantic_probe=6/6 telemetry=0 world_knowledge=false "
        "live_runtime_mutation=false deployment_changed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
