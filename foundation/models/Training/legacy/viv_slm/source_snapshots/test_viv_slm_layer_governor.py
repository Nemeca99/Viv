#!/usr/bin/env python3
"""Focused tests for the reusable bounded layer governor."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.viv_slm_layer_governor import (  # noqa: E402
    adaptive_controller_update,
    guarded_rollback_decision,
    evaluate_scale_ladder,
    parent_binding_matches,
    require_one_increment,
    seed_controller_actuation_state,
    select_largest_guard_safe_trial,
    validate_authority_record,
    validate_layer_campaign_spec,
)


def main() -> int:
    contract_path = FOUNDATION / "artifacts" / "auto" / "agentic" / "layer_campaign_contracts" / "V36_COMPOSED_BEHAVIOR_LAYER.json"
    contract = validate_layer_campaign_spec(json.loads(contract_path.read_text(encoding="utf-8")))
    assert contract.campaign_id.endswith("_0250")
    assert contract.allowed_scale_ladder == (1.0, 0.75, 0.5, 0.25, 0.1)
    assert contract.step_budget == 250 and contract.rollback_budget == 2
    assert contract.authority_scope["promotion_authorized"] is False
    assert validate_layer_campaign_spec(contract.to_mapping()).to_mapping() == contract.to_mapping()

    assert require_one_increment(250) == 250
    for invalid_steps in (0, 1, 500):
        try:
            require_one_increment(invalid_steps)
        except ValueError as error:
            assert "250" in str(error)
        else:
            raise AssertionError("non-250 increment was accepted")

    authority = validate_authority_record(
        {
            "campaign_id": "campaign",
            "training_authorized": True,
            "run_authorized": True,
            "promotion_authorized": False,
            "deployment_changed": False,
            "live_model_changed": False,
            "global_aifl_writes": False,
            "master_s_n_mutation": False,
            "knowledge_admission": False,
            "scope": {"steps": 250},
        },
        campaign_id="campaign",
        steps=250,
    )
    assert authority["steps"] == 250
    try:
        validate_authority_record(
            {**authority, "promotion_authorized": True, "scope": {"steps": 250}},
            campaign_id="campaign",
            steps=250,
        )
    except PermissionError as error:
        assert "side_effect_gate_open" in str(error)
    else:
        raise AssertionError("open promotion gate was accepted")

    selected = select_largest_guard_safe_trial(
        [
            {"scale": 1.0, "metric_guard": False, "behavior_guard": True, "improved": True},
            {"scale": 0.75, "metric_guard": True, "behavior_guard": True, "improved": True},
            {"scale": 0.5, "metric_guard": True, "behavior_guard": True, "improved": True},
        ]
    )
    assert selected is not None
    assert selected["scale"] == 0.75 and selected["selected"] is True
    assert select_largest_guard_safe_trial(
        [{"scale": 0.5, "metric_guard": True, "behavior_guard": True, "improved": False}]
    ) is None

    parent_state = {
        "weight": torch.tensor([0.2, 0.5]),
        "integer_buffer": torch.tensor([3], dtype=torch.long),
    }
    child_state = {
        "weight": torch.tensor([0.4, 0.9]),
        "integer_buffer": torch.tensor([8], dtype=torch.long),
    }
    source_parent_state = {
        "weight": torch.tensor([0.2, 0.5]),
        "integer_buffer": torch.tensor([1], dtype=torch.long),
    }
    ladder_result = evaluate_scale_ladder(
        parent_state=parent_state,
        delta_source_child_state=child_state,
        delta_source_parent_state=source_parent_state,
        allowed_scale_ladder=(1.0, 0.75, 0.5),
        evaluate_candidate=lambda state: {
            "nll": float(state["weight"][0]),
            "accuracy": float(state["weight"][1]),
        },
        guard_candidate=lambda baseline, candidate: {
            "metric_guard": candidate["nll"] <= baseline["nll"] + 0.16,
            "behavior_guard": candidate["accuracy"] >= baseline["accuracy"],
        },
        improvement_candidate=lambda baseline, candidate: candidate["accuracy"] > baseline["accuracy"],
    )
    assert ladder_result["selected_scale"] == 0.75
    assert ladder_result["selected_trial"]["selected"] is True
    assert torch.equal(ladder_result["selected_state"]["integer_buffer"], parent_state["integer_buffer"])
    assert torch.equal(parent_state["weight"], torch.tensor([0.2, 0.5]))

    passing = guarded_rollback_decision(
        guards={"metric": True, "behavior": True},
        consecutive_guard_failures=1,
    )
    assert passing["rollback"] is False
    assert passing["consecutive_guard_failures"] == 0
    first_failure = guarded_rollback_decision(
        guards={"metric": False, "behavior": True},
        consecutive_guard_failures=0,
    )
    assert first_failure["rollback"] is True and first_failure["halt"] is False
    second_failure = guarded_rollback_decision(
        guards={"metric": False, "behavior": True},
        consecutive_guard_failures=1,
    )
    assert second_failure["rollback"] is True and second_failure["halt"] is True

    parent = {"checkpoint": "L:/parent.pt", "checkpoint_sha256": "ABC"}
    assert parent_binding_matches({"warm_start_checkpoint_sha256": "abc"}, parent) is True
    assert parent_binding_matches({"warm_start_checkpoint_sha256": "DEF"}, parent) is False
    assert parent_binding_matches({"warm_start_checkpoint": "L:\\parent.pt"}, {"checkpoint": "L:/parent.pt"}) is True

    controller_seed = {
        "teacher_kl_delta_ema": 0.0,
        "validation_nll_delta_ema": 0.0,
        "anchor_weight": 0.20,
        "lr_scale": 1.0,
    }
    stable_controller = adaptive_controller_update(
        controller_seed,
        observations={
            "teacher_kl_delta": 0.0,
            "validation_nll_delta": 0.0,
            "training_nll": 0.20,
            "sft_loss": 0.20,
            "total_loss": 0.22,
            "grad_norm_before_clip": 0.50,
        },
        max_grad_norm=1.0,
    )
    assert stable_controller["loss_pressure"] == 0.0
    assert stable_controller["gradient_pressure"] == 0.0
    assert stable_controller["schema_version"] == "viv_slm_multi_metric_controller_v1"
    assert "gradient_clip_scale" not in stable_controller
    assert stable_controller["lr_scale"] == 1.0
    assert stable_controller["anchor_weight"] == 0.20
    unstable_controller = adaptive_controller_update(
        stable_controller,
        observations={
            "teacher_kl_delta": 0.004,
            "validation_nll_delta": 0.002,
            "training_nll": 0.24,
            "sft_loss": 0.25,
            "total_loss": 0.30,
            "grad_norm_before_clip": 0.95,
        },
        config={"ema_alpha": 1.0},
        max_grad_norm=1.0,
    )
    assert unstable_controller["loss_pressure"] > 0.0
    assert unstable_controller["gradient_pressure"] > 0.0
    assert unstable_controller["stability_pressure"] > 0.0
    assert unstable_controller["lr_scale"] < stable_controller["lr_scale"]
    assert unstable_controller["anchor_weight"] > stable_controller["anchor_weight"]
    assert 0.20 <= unstable_controller["lr_scale"] <= 1.05
    assert 0.05 <= unstable_controller["anchor_weight"] <= 0.50
    v2_controller = adaptive_controller_update(
        controller_seed,
        observations={
            "teacher_kl_delta": 0.0,
            "validation_nll_delta": 0.0,
            "training_nll": 0.20,
            "sft_loss": 0.20,
            "total_loss": 0.22,
            "grad_norm_before_clip": 0.95,
        },
        config={"schema_version": "viv_slm_multi_metric_controller_v2", "ema_alpha": 1.0},
        max_grad_norm=1.0,
        gradient_clip_scale_min=0.75,
        gradient_clip_scale_max=1.0,
    )
    assert v2_controller["gradient_pressure"] > 0.0
    assert v2_controller["schema_version"] == "viv_slm_multi_metric_controller_v2"
    assert v2_controller["controller_config"]["schema_version"] == "viv_slm_multi_metric_controller_v2"
    assert 0.75 <= v2_controller["gradient_clip_scale"] < 1.0
    assert v2_controller["gradient_clip_ceiling"] < 1.0
    assert "gradient_clip_scale" in v2_controller["tuned_variables"]
    assert "weight_decay_scale" not in v2_controller
    v3_controller = adaptive_controller_update(
        controller_seed,
        observations={
            "teacher_kl_delta": 0.004,
            "validation_nll_delta": 0.002,
            "training_nll": 0.24,
            "sft_loss": 0.25,
            "total_loss": 0.30,
            "grad_norm_before_clip": 0.95,
        },
        config={"schema_version": "viv_slm_multi_metric_controller_v3", "ema_alpha": 1.0},
        max_grad_norm=1.0,
        base_weight_decay=0.01,
        gradient_clip_scale_min=0.75,
        gradient_clip_scale_max=1.0,
        weight_decay_scale_min=0.25,
        weight_decay_scale_max=1.0,
    )
    assert v3_controller["schema_version"] == "viv_slm_multi_metric_controller_v3"
    assert v3_controller["gradient_clip_scale"] < 1.0
    assert 0.25 <= v3_controller["weight_decay_scale"] < 1.0
    assert v3_controller["effective_weight_decay"] < 0.01
    assert "weight_decay_scale" in v3_controller["tuned_variables"]
    seeded_controller = seed_controller_actuation_state(
        controller_seed,
        {
            "schema_version": "viv_slm_multi_metric_controller_v3",
            "anchor_weight": 0.31,
            "lr_scale": 0.68,
            "gradient_clip_scale": 0.90,
            "weight_decay_scale": 0.60,
            "metric_ema": {"total_loss": 999.0},
            "metric_baselines": {"total_loss": 999.0},
        },
        expected_schema_version="viv_slm_multi_metric_controller_v3",
        anchor_weight_min=0.05,
        anchor_weight_max=0.50,
        learning_rate_scale_min=0.20,
        learning_rate_scale_max=1.05,
        gradient_clip_scale_min=0.75,
        gradient_clip_scale_max=1.00,
        weight_decay_scale_min=0.25,
        weight_decay_scale_max=1.00,
    )
    assert seeded_controller["anchor_weight"] == 0.31
    assert seeded_controller["lr_scale"] == 0.68
    assert seeded_controller["gradient_clip_scale"] == 0.90
    assert seeded_controller["weight_decay_scale"] == 0.60
    assert "metric_ema" not in seeded_controller
    assert "metric_baselines" not in seeded_controller
    assert seeded_controller["controller_seed"]["metric_history_carried"] is False
    try:
        seed_controller_actuation_state(
            controller_seed,
            {"schema_version": "viv_slm_multi_metric_controller_v3", "anchor_weight": 0.60, "lr_scale": 0.68, "gradient_clip_scale": 0.90, "weight_decay_scale": 0.60},
            expected_schema_version="viv_slm_multi_metric_controller_v3",
            anchor_weight_min=0.05,
            anchor_weight_max=0.50,
            learning_rate_scale_min=0.20,
            learning_rate_scale_max=1.05,
            gradient_clip_scale_min=0.75,
            gradient_clip_scale_max=1.00,
            weight_decay_scale_min=0.25,
            weight_decay_scale_max=1.00,
        )
    except ValueError as error:
        assert "out_of_bounds" in str(error)
    else:
        raise AssertionError("out-of-bounds controller seed was accepted")
    try:
        adaptive_controller_update(
            controller_seed,
            observations={"grad_norm_before_clip": float("nan")},
        )
    except ValueError as error:
        assert "nonfinite" in str(error)
    else:
        raise AssertionError("non-finite controller observation was accepted")

    print(
        "VIV_SLM_LAYER_GOVERNOR_PREFLIGHT_PASS "
        "increment_bound=true authority_closed=true largest_safe_scale=true "
        "rollback_budget=true parent_binding=true side_effect_free=true "
        "multi_metric_autotune=true gradient_loss_feedback=true"
        " gradient_clip_feedback=true weight_decay_feedback=true controller_state_layering=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
