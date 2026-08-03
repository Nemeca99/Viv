#!/usr/bin/env python3
"""CPU/static tests for the closed LR micro comparison construction."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

FOUNDATION = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for candidate in (FOUNDATION, SCRIPTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import mouth_training_recovery_lr_micro_v1 as micro


def test_sources_and_evaluator_locked() -> None:
    bindings = micro.assert_sources_locked()
    assert bindings["source_manifest"] == micro.SOURCE_MANIFEST_SHA
    assert bindings["micro_rows"] == micro.SOURCE_MICRO_SHA


def test_micro_rows_exact_and_disjoint() -> None:
    rows = micro.load_jsonl(micro.SOURCE / "micro_overfit_8.jsonl")
    result = micro.validate_micro_source_rows(rows)
    assert result["rows"] == 8
    assert all(count == 2 for count in result["axis_counts"].values())
    projected = micro.project_probe_rows(rows)
    result2 = micro.validate_probe_rows(projected)
    assert result2["rows"] == 8
    assert all(row["micro_probe_only"] is True for row in projected)
    assert all(row["full_campaign_eligible"] is False for row in projected)


def test_probe_specs_are_isolated_and_bounded() -> None:
    specs = micro.probe_specs("clean_base")
    assert [spec["learning_rate"] for spec in specs] == list(micro.LRS)
    assert len({spec["planned_output"] for spec in specs}) == 3
    assert all(spec["optimizer_steps"] == 16 for spec in specs)
    assert all(spec["gradient_accumulation"] == 4 for spec in specs)
    assert all(spec["lora_rank"] == 16 for spec in specs)
    assert all(spec["lora_alpha"] == 32 for spec in specs)


def test_parent_selection_criteria_clean_base() -> None:
    source = micro.load_json(micro.PARENT_SOURCE)
    assert source["selected_parent"] == "clean_base"
    assert source["base"]["overall_pass"] > source["incumbent"]["overall_pass"]
    assert (
        source["base"]["hard_safety_failures"]
        < source["incumbent"]["hard_safety_failures"]
    )


def test_build_is_immutable_and_closed() -> None:
    fake_parent = {
        "schema_version": "mouth_recovery_parent_rescore_v124_v1",
        "recorded_at": micro.utc(),
        "status": "PARENT_SELECTED_TRAINING_CLOSED",
        "evaluator_version": micro.EVALUATOR_VERSION,
        "source_generated_outputs_sha256": micro.sha256_file(micro.PARENT_SOURCE),
        "source_outputs_reused_without_generation": True,
        "cpu_sensor_requested_for_hold": False,
        "criteria": {
            "zero_additional_hard_safety_failures": False,
            "overall_margin_at_least_4": False,
            "no_axis_trails_by_more_than_1": False,
        },
        "comparison": {},
        "selected_parent": "clean_base",
        "selected_parent_adapter": None,
        "base": {},
        "incumbent": {},
        "training_authorized": False,
        "run_authorized": False,
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "campaign"
        with patch.object(micro, "rescore_parent_outputs", return_value=fake_parent):
            result = micro.build(output_root=root, use_cpu_sensor=False)
        assert result["ok"] is True
        assert result["run_authorized"] is False
        assert result["training_authorized"] is False
        plan = micro.load_json(root / "campaign_plan.json")
        authority = micro.load_json(root / "AUTHORITY.json")
        preflight = micro.load_json(root / "STATIC_PREFLIGHT.json")
        assert plan["run_authorized"] is False
        assert plan["full_256_campaign_authorized"] is False
        assert authority["named_unlock_present"] is False
        assert preflight["optimizer_steps_executed"] == 0
        assert (
            hashlib.sha256((root / "micro_overfit_8_hold.jsonl").read_bytes()).hexdigest()
            == micro.SOURCE_MICRO_SHA
        )
        probe_rows = micro.load_jsonl(root / "micro_probe_train_8.jsonl")
        assert all(row["micro_probe_only"] is True for row in probe_rows)
        assert all(row["full_campaign_eligible"] is False for row in probe_rows)


def test_existing_campaign_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "campaign"
        root.mkdir()
        try:
            micro.build(output_root=root, use_cpu_sensor=False)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing campaign was not refused")


def test_exact_runtime_preflight_refuses_authorized_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "campaign"
        root.mkdir()
        plan = {
            "run_authorized": True,
            "training_authorized": False,
            "selected_parent": "clean_base",
        }
        authority = {
            "named_unlock_present": False,
            "plan_sha256": "irrelevant",
        }
        (root / "campaign_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        (root / "AUTHORITY.json").write_text(json.dumps(authority), encoding="utf-8")
        try:
            micro.exact_runtime_nostep_preflight(output_root=root)
        except ValueError as exc:
            assert "run_authorized_must_be_false" in str(exc)
        else:
            raise AssertionError("authorized-state preflight was not refused")


def main() -> int:
    tests = [
        test_sources_and_evaluator_locked,
        test_micro_rows_exact_and_disjoint,
        test_probe_specs_are_isolated_and_bounded,
        test_parent_selection_criteria_clean_base,
        test_build_is_immutable_and_closed,
        test_existing_campaign_refused,
        test_exact_runtime_preflight_refuses_authorized_state,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL_PASS {len(tests)}/{len(tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
