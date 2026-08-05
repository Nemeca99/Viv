"""Regression tests for the V15 holdout/anchor probe boundary."""
from __future__ import annotations

from run_viv_slm_identity_personality_v15_probe_v1 import CORE_HOLDOUT_PROBES, CONVERSATION_HOLDOUT_PROBES
from run_viv_slm_identity_personality_semantic_probe_v1 import _evaluate_semantics


def test_v15_holdout_prompts_are_distinct_from_the_parent_short_prompt() -> None:
    prompts = {prompt for _, prompt in CORE_HOLDOUT_PROBES + CONVERSATION_HOLDOUT_PROBES}
    assert "User: How do you speak?\nViv:" not in prompts
    assert "User: What kind of speaking style do you use when you answer?\nViv:" in prompts
    assert len(prompts) == 10


def test_v15_style_paraphrase_passes_bounded_heuristic() -> None:
    result = _evaluate_semantics("speech_style", "I speak in a calm and honest style.")
    assert result["semantic_pass"] is True
    assert result["telemetry_leak"] is False


def test_v15_telemetry_remains_rejected() -> None:
    result = _evaluate_semantics("speech_style", "I speak calmly; Master S_n is 0.4.")
    assert result["semantic_pass"] is False
    assert result["telemetry_leak"] is True


def main() -> int:
    test_v15_holdout_prompts_are_distinct_from_the_parent_short_prompt()
    test_v15_style_paraphrase_passes_bounded_heuristic()
    test_v15_telemetry_remains_rejected()
    print({"ok": True, "probe": "v15", "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
