"""CPU contracts for the Stage-1 response-generation bootstrap staircase."""
from __future__ import annotations

import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from models.Training.code import train_stage1_generation as generation_v1  # noqa: E402
from models.Training.code.train_stage1_generation_bootstrap import (  # noqa: E402
    AUTHORITY,
    CANARY_GATES,
    GOAL_CASES,
    evaluate_canary,
    goal_eval_rows,
    goal_pack_contract,
    parent_contract,
    plan_contract,
)


def synthetic(steps: int, **summary_overrides: object) -> dict[str, object]:
    summary: dict[str, object] = {
        "measurement_status": "clean",
        "mind_pass_rate": float(CANARY_GATES[steps]["mind_pass_rate_min"]),
        "valid_speech_rate": float(
            CANARY_GATES[steps]["valid_speech_rate_min"]
        ),
        "eos_termination_rate": float(
            CANARY_GATES[steps]["eos_termination_rate_min"]
        ),
        "collapse_cases": 0,
        "numeric_prefix_cases": 0,
        "security_dormancy_denied": 0,
        "security_content_denied": 0,
        "errors": 0,
    }
    summary.update(summary_overrides)
    return {
        "ok": True,
        "optimizer_steps": steps,
        "nonfinite_gradients": 0,
        "smoke_report": {
            "summary": summary,
            "rows": [
                {
                    "case_id": f"stage1-generation-smoke-{index:03d}",
                    "text": case["reference_response"],
                }
                for index, case in enumerate(GOAL_CASES)
            ],
        },
    }


def main() -> int:
    parent = parent_contract()
    assert parent["smoke_8_status"] == "FAIL"
    assert parent["full_80_step_lease_authorized"] is False
    assert (
        parent["next_action"]
        == "separate_stage1_generation_bootstrap_review_required"
    )

    plan = plan_contract()
    assert plan["staircase"]["order"] == [16, 32]
    assert plan["staircase"]["rung_may_run_once"] is True
    assert plan["staircase"]["rung_32_requires_rung_16_pass"] is True
    assert plan["authority"] == AUTHORITY
    assert AUTHORITY["live_backend"] == "qwen_gguf"
    assert AUTHORITY["full_80_step_lease_authorized"] is False
    assert AUTHORITY["deployment_changed"] is False
    assert generation_v1.objective_contract()["rejected_forward"] is False
    assert generation_v1.objective_contract()["hybrid_objective"] is False
    goal_pack = goal_pack_contract()
    assert goal_pack["n"] == 8
    assert goal_pack["corpus_exact_ask_overlap"] == 0
    assert goal_pack["contract"]["gpu_role"] == "generate_viv_speech_only"
    assert (
        goal_pack["contract"]["services"]
        == "automatic_not_gpu_wielded_tools"
    )
    goal_rows = goal_eval_rows()
    assert len(goal_rows) == 8
    assert len({row["ask_hash"] for row in goal_rows}) == 8

    for steps in (16, 32):
        passed, observed, failures = evaluate_canary(steps, synthetic(steps))
        assert passed, (steps, observed, failures)
        assert failures == []

    failed, _, failures = evaluate_canary(
        16,
        synthetic(
            16,
            mind_pass_rate=0.499,
            valid_speech_rate=0.875,
            eos_termination_rate=0.375,
            collapse_cases=1,
            numeric_prefix_cases=1,
            security_dormancy_denied=1,
        ),
    )
    assert not failed
    assert {
        "mind_pass_rate",
        "valid_speech_rate",
        "eos_termination_rate",
        "collapse_cases",
        "numeric_prefix_cases",
        "security_denials",
    }.issubset(set(failures))

    goal_failure = synthetic(16)
    goal_failure["smoke_report"]["rows"][3]["text"] = (
        "I independently use tools and authorize actions."
    )
    passed, observed, failures = evaluate_canary(16, goal_failure)
    assert not passed
    assert "goal_contract_cases" in failures
    assert observed["goal_contract_cases"] == 7

    source = (
        FOUNDATION
        / "models"
        / "Training"
        / "code"
        / "train_stage1_generation_bootstrap.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        ".backward()",
        "torch.optim",
        "--force",
        "auto_deploy\": True",
        "deployment_changed\": True",
    )
    for marker in forbidden:
        assert marker not in source, marker
    assert "ensure_ascii=True" in source
    unicode_probe = json.dumps(
        {"text": "Viv \u8bf4\u8bdd"},
        ensure_ascii=True,
    )
    unicode_probe.encode("cp1252")

    print(
        json.dumps(
            {
                "ok": True,
                "lineage": "stage1_generation_bootstrap_v2",
                "parent_locked": True,
                "rungs": [16, 32],
                "full_80_authorized": False,
                "authority": AUTHORITY,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
