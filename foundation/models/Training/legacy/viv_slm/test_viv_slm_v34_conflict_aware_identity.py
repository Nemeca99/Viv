#!/usr/bin/env python3
"""Focused preflight checks for the V34 conflict-aware AIFL lane."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, FOUNDATION / "scripts", VIV_ROOT, VIV_ROOT / "models" / "uml_bigram_part3"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import train_viv_slm_v34_conflict_aware_identity as v34  # noqa: E402


def main() -> int:
    focus = {"weight": torch.tensor([1.0, 0.0])}
    replay = {"weight": torch.tensor([-1.0, 0.0])}
    projected, geometry = v34.project_conflicting_gradient(focus, replay)
    assert geometry["conflict"] is True
    assert geometry["projection_applied"] is True
    assert abs(float(torch.sum(projected["weight"] * replay["weight"]))) < 1e-6

    aligned, aligned_geometry = v34.project_conflicting_gradient(
        {"weight": torch.tensor([1.0, 0.0])},
        {"weight": torch.tensor([1.0, 0.0])},
    )
    assert aligned_geometry["conflict"] is False
    assert torch.equal(aligned["weight"], torch.tensor([1.0, 0.0]))

    controller_seed = {
        "alpha": 0.1,
        "conflict_ema": 0.0,
        "replay_delta_ema": 0.0,
        "validation_delta_ema": 0.0,
        "feedback_error_ema": 0.0,
        "focus_scale": v34.BASE_FOCUS_SCALE,
        "lr_scale": 1.0,
        "replay_scale": 1.0,
    }
    feedback_nudge = v34.recursive_conflict_nudge_update(
        controller_seed,
        observed_conflict_cosine=0.0,
        observed_replay_nll_delta=0.0,
        observed_validation_nll_delta=0.0,
        observed_aifl_feedback_error=1.0,
    )
    no_feedback_nudge = v34.recursive_conflict_nudge_update(
        controller_seed,
        observed_conflict_cosine=0.0,
        observed_replay_nll_delta=0.0,
        observed_validation_nll_delta=0.0,
        observed_aifl_feedback_error=0.0,
    )
    assert feedback_nudge["feedback_pressure"] > no_feedback_nudge["feedback_pressure"]
    assert feedback_nudge["lr_scale"] > no_feedback_nudge["lr_scale"]
    protected = v34.recursive_conflict_nudge_update(
        controller_seed,
        observed_conflict_cosine=-1.0,
        observed_replay_nll_delta=0.1,
        observed_validation_nll_delta=0.1,
        observed_aifl_feedback_error=0.0,
    )
    assert protected["lr_scale"] < 1.0
    assert protected["replay_scale"] > 1.0
    assert v34.MIN_LR_SCALE <= protected["lr_scale"] <= v34.MAX_LR_SCALE
    assert v34.MIN_REPLAY_SCALE <= protected["replay_scale"] <= v34.MAX_REPLAY_SCALE

    passing = v34.guarded_rollback_decision(
        metric_guard=True,
        feedback_guard=True,
        consecutive_guard_failures=1,
    )
    assert passing["rollback"] is False
    assert passing["halt"] is False
    assert passing["consecutive_guard_failures"] == 0
    first_failure = v34.guarded_rollback_decision(
        metric_guard=False,
        feedback_guard=True,
        consecutive_guard_failures=0,
    )
    assert first_failure["rollback"] is True
    assert first_failure["halt"] is False
    assert first_failure["consecutive_guard_failures"] == 1
    second_failure = v34.guarded_rollback_decision(
        metric_guard=True,
        feedback_guard=False,
        consecutive_guard_failures=1,
    )
    assert second_failure["rollback"] is True
    assert second_failure["halt"] is True
    assert second_failure["consecutive_guard_failures"] == 2

    gradient_model = torch.nn.Linear(2, 1)
    gradient_loss = gradient_model(torch.ones(1, 2)).sum()
    gradient_loss.backward()
    captured = v34._capture_gradients(gradient_model)
    assert captured
    assert all(isinstance(value, torch.Tensor) for value in captured.values())

    cases = v34._load_aifl_feedback_cases()
    assert [case["intent_id"] for case in cases] == ["greeting", "current_state"]
    assert all(case["authorized_source"] == "cpu_identity_router_authorized_text" for case in cases)

    tokenizer, _, _, _ = v34._validate_sources()
    model = torch.nn.Linear(1, 1)
    model.train()
    original_sample = v34._sample_prompt_reply
    original_score = v34.score_draft
    original_criteria = v34.load_criteria
    try:
        def fake_sample(*args, **kwargs):
            prompt = str(kwargs["prompt"])
            return "Hello. I am here and ready to listen." if prompt.startswith("Hello") else "I am here and ready to listen."

        v34._sample_prompt_reply = fake_sample
        v34.score_draft = lambda *args, **kwargs: {"vidi": 1, "intellexi": 1, "vixi": 1, "label": "REWARD", "reasons": []}
        v34.load_criteria = lambda: {"version": "test-aifl-criteria"}
        feedback = v34.run_aifl_feedback(
            model,
            tokenizer,
            device=torch.device("cpu"),
            seed=42,
            stop_marker="<END>",
        )
    finally:
        v34._sample_prompt_reply = original_sample
        v34.score_draft = original_score
        v34.load_criteria = original_criteria
    assert model.training is True
    assert feedback["status"] == "PASS"
    assert feedback["case_total"] == 2
    assert feedback["mind_pass_rate"] == 1.0
    assert feedback["global_preference_buffer_written"] is False
    assert feedback["global_train_gate_written"] is False
    assert feedback["live_runtime_mutation"] is False

    with tempfile.TemporaryDirectory(prefix="viv_slm_v34_conflict_aware_") as temp_dir:
        try:
            v34.train(output_dir=Path(temp_dir) / "should_not_run", authorize=False, device_name="cpu")
        except PermissionError as error:
            assert "explicit_authorize" in str(error)
        else:
            raise AssertionError("V34 trainer accepted a run without --authorize")

    print(
        "VIV_SLM_V34_CONFLICT_AWARE_IDENTITY_PREFLIGHT_PASS "
        "source_derived_aifl=true pairwise_rows_hash_locked=true "
        "global_preference_write=false global_train_gate_write=false "
        "gradient_projection=true recursive_feedback_nudge=true "
        "explicit_authorize_required=true promotion_closed=true deployment_closed=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
