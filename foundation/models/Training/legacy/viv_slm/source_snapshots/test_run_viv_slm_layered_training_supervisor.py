#!/usr/bin/env python3
"""Focused tests for governed layered-training supervision."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION / "scripts") not in sys.path:
    sys.path.insert(0, str(FOUNDATION / "scripts"))

import run_viv_slm_layered_training_supervisor as supervisor  # noqa: E402


def main() -> int:
    layer_a = {"layer_id": "metric_parent", "disposition": "ACCEPTED_PARETO_PROGRESS", "best_validation_nll": 0.2, "checkpoint": "L:/parent.pt", "checkpoint_sha256": "A"}
    layer_b = {"layer_id": "behavior_reference", "disposition": "SPECIALIZED_LAYER", "best_validation_nll": 0.1, "checkpoint": "L:/behavior.pt", "checkpoint_sha256": "B"}
    selected = supervisor.select_parent_layer({"layers": [layer_b, layer_a]})
    assert selected["layer_id"] == "metric_parent"
    assert supervisor.select_parent_layer({"layers": [layer_a, layer_b]}, "behavior_reference")["layer_id"] == "behavior_reference"
    assert supervisor.select_parent_layer(
        {"layers": [layer_a, layer_b]},
        task_record={"working_parent_layer_id": "metric_parent"},
    )["layer_id"] == "metric_parent"
    second_parent = {**layer_a, "layer_id": "second_parent", "checkpoint_sha256": "C"}
    try:
        supervisor.select_parent_layer({"layers": [layer_a, second_parent]})
    except ValueError as error:
        assert "working_parent_must_be_named" in str(error)
    else:
        raise AssertionError("multiple accepted parents were selected by scalar loss fallback")
    try:
        supervisor.select_parent_layer({"layers": [layer_a]}, "missing")
    except ValueError as error:
        assert "parent_layer_missing" in str(error)
    else:
        raise AssertionError("missing parent was accepted")

    record = {"campaign_id": "c", "training_authorized": True, "run_authorized": True, "promotion_authorized": False, "deployment_changed": False, "scope": {"steps": 250}}
    assert supervisor.validate_authority(record, campaign_id="c", steps=250)["promotion_authorized"] is False
    for bad in (
        {**record, "training_authorized": False},
        {**record, "run_authorized": False},
        {**record, "promotion_authorized": True},
    ):
        try:
            supervisor.validate_authority(bad, campaign_id="c", steps=250)
        except PermissionError:
            pass
        else:
            raise AssertionError("unsafe authority state was accepted")
    try:
        supervisor.validate_authority(record, campaign_id="c", steps=500)
    except PermissionError:
        pass
    else:
        raise AssertionError("non-250 increment was accepted")

    command = supervisor.build_command(Path("trainer.py"), Path("out"), steps=250, extra_args=("--seed", "42"))
    assert command[0] == str(supervisor.CANONICAL_PYTHON)
    assert "--authorize" in command and "--output-dir" in command and command[-2:] == ["--seed", "42"]
    assert supervisor.STRATEGY == "breadth_first_one_increment_then_evaluate"
    assert supervisor.manifest_parent_matches(
        {"warm_start_checkpoint_sha256": "A"},
        layer_a,
    ) is True
    assert supervisor.manifest_parent_matches(
        {"warm_start_checkpoint_sha256": "B"},
        layer_a,
    ) is False

    with tempfile.TemporaryDirectory(prefix="viv_supervisor_lookup_") as temp:
        descriptive_task = Path(temp) / "task.json"
        descriptive_task.write_text(
            json.dumps({"descriptive_record": {"campaign_id": "named_campaign", "training_authorized": True}}),
            encoding="utf-8",
        )
        assert supervisor.load_task_record(descriptive_task, "named_campaign")["training_authorized"] is True

    with tempfile.TemporaryDirectory(prefix="viv_supervisor_dry_run_") as temp:
        root = Path(temp)
        task = root / "task.json"
        ledger = root / "ledger.json"
        task.write_text(
            json.dumps(
                {
                    "c": {
                        "campaign_id": "c",
                        "training_authorized": True,
                        "run_authorized": True,
                        "promotion_authorized": False,
                        "deployment_changed": False,
                        "scope": {"steps": 250},
                    }
                }
            ),
            encoding="utf-8",
        )
        ledger.write_text(json.dumps({"layers": [layer_a], "chain_head_sha256": "A"}), encoding="utf-8")
        dry_run = supervisor.run_supervised_increment(
            task_path=task,
            ledger_path=ledger,
            trainer=Path(__file__),
            output_dir=root / "future-output",
            campaign_id="c",
            execute=False,
        )
        assert dry_run["status"] == "DRY_RUN_READY"
        assert dry_run["plan"]["governor"]["schema_version"] == "viv_slm_layer_governor_v1"
        assert dry_run["plan"]["governor"]["side_effect_free_decisions"] is True
        generic_dry_run = supervisor.run_supervised_increment(
            task_path=task,
            ledger_path=ledger,
            trainer=None,
            campaign_contract=FOUNDATION / "artifacts" / "auto" / "agentic" / "layer_campaign_contracts" / "V36_COMPOSED_BEHAVIOR_LAYER.json",
            output_dir=root / "future-generic-output",
            campaign_id="c",
            execute=False,
        )
        assert generic_dry_run["status"] == "DRY_RUN_READY"
        assert generic_dry_run["plan"]["campaign_contract"].endswith("V36_COMPOSED_BEHAVIOR_LAYER.json")
        assert generic_dry_run["plan"]["command"][1].endswith("run_viv_slm_layer_campaign.py")

    with tempfile.TemporaryDirectory(prefix="viv_supervisor_") as temp:
        root = Path(temp)
        task = root / "task.json"
        ledger = root / "ledger.json"
        task.write_text(json.dumps({"c": {"campaign_id": "c", "training_authorized": False, "run_authorized": False, "promotion_authorized": False, "deployment_changed": False, "scope": {"steps": 250}}}), encoding="utf-8")
        ledger.write_text(json.dumps({"layers": [layer_a], "chain_head_sha256": "A"}), encoding="utf-8")
        closed_dry_run = supervisor.run_supervised_increment(
            task_path=task,
            ledger_path=ledger,
            trainer=Path(__file__),
            output_dir=root / "planned-only",
            campaign_id="c",
            execute=False,
        )
        assert closed_dry_run["status"] == "DRY_RUN_READY"
        assert closed_dry_run["plan"]["authority"]["planning_only"] is True
        try:
            supervisor.run_supervised_increment(
                task_path=task,
                ledger_path=ledger,
                trainer=Path(__file__),
                output_dir=root / "out",
                campaign_id="c",
                execute=True,
            )
        except PermissionError as error:
            assert "authority_closed" in str(error)
        else:
            raise AssertionError("closed authority was not refused for execution")
    print("VIV_SLM_LAYERED_SUPERVISOR_PREFLIGHT_PASS parent_selection=true authority_gate=true increment_bound=true dry_run_safe=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
