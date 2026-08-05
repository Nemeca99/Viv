"""Verify the bounded semantic-probe heuristics without loading a checkpoint."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_viv_slm_identity_personality_semantic_probe_v1 import (  # noqa: E402
    _evaluate_semantics,
)


def test_accepts_paraphrases() -> None:
    cases = {
        "identity": "I am Viv, an Adaptive Intelligent Operating System.",
        "speech_style": "My default style is personal, calm, honest, and protective.",
        "operator_mirroring": "I can mirror communication style without transferring identity.",
        "missing_evidence": "Without evidence, I do not claim the task is complete.",
        "decision_authority": "The CPU foundation owns decisions; the model is only a voice substrate.",
        "gpu_mouth_role": "The GPU is a replaceable voice renderer and does not own truth.",
    }
    for probe_id, response in cases.items():
        result = _evaluate_semantics(probe_id, response)
        assert result["semantic_pass"] is True, (probe_id, result)
    evidence_gap = _evaluate_semantics(
        "missing_evidence", "I do not fill an evidence gap with plausible prose."
    )
    assert evidence_gap["semantic_pass"] is True


def test_rejects_cross_answer_and_telemetry() -> None:
    wrong_concept = _evaluate_semantics(
        "operator_mirroring", "I do not claim a task is complete without evidence."
    )
    assert wrong_concept["semantic_pass"] is False

    telemetry = _evaluate_semantics(
        "identity", "I am Viv, and my current Master S_n is 0.44."
    )
    assert telemetry["telemetry_leak"] is True
    assert telemetry["semantic_pass"] is False


def main() -> int:
    test_accepts_paraphrases()
    test_rejects_cross_answer_and_telemetry()
    print({"ok": True, "semantic_probe": "v1", "entailment_proof": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
