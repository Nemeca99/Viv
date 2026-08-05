#!/usr/bin/env python3
"""Run one governed Viv-SLM training increment and register its layer.

This supervisor owns orchestration, not model authority. It selects a parent
from the append-only ledger, verifies the current task's exact authority, runs
one bounded increment through the canonical Python runtime, and registers the
result only when the produced manifest binds to the checkpoint hash. It never
promotes, deploys, mutates live state, or changes the task authority record.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from paths import (  # noqa: E402
    CANONICAL_PYTHON,
    FOUNDATION,
    TRAINING_ROOT,
    VIV_ROOT,
    VIV_SLM_ROOT,
)
for path in (FOUNDATION, VIV_ROOT, VIV_SLM_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from viv_slm_layer_governor import (  # noqa: E402
    parent_binding_matches as _governor_parent_binding_matches,
    require_one_increment,
)

CURRENT_TASK = FOUNDATION / "artifacts" / "auto" / "agentic" / "CURRENT_TASK.json"
DEFAULT_LEDGER = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_checkpoint_layers.json"
DEFAULT_EVIDENCE_ROOT = FOUNDATION / "artifacts" / "auto" / "agentic" / "layered_supervisor"
DEFAULT_LAYER_ENGINE = VIV_SLM_ROOT / "run_viv_slm_layer_campaign.py"
INCREMENT = 250
STRATEGY = "breadth_first_one_increment_then_evaluate"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"supervisor_expected_json_object:{path}")
    return value


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_task_record(task_path: Path, campaign_id: str) -> dict[str, Any]:
    task = _read_json(task_path)
    record = task.get(campaign_id)
    if isinstance(record, dict):
        return record
    matches = [
        value
        for value in task.values()
        if isinstance(value, dict) and value.get("campaign_id") == campaign_id
    ]
    if len(matches) == 1:
        return matches[0]
    raise PermissionError("supervisor_named_campaign_record_missing")


def select_parent_layer(
    ledger: dict[str, Any],
    parent_layer_id: str | None = None,
    *,
    task_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    layers = ledger.get("layers")
    if not isinstance(layers, list):
        raise ValueError("supervisor_layer_ledger_invalid")
    candidates = [item for item in layers if isinstance(item, dict)]
    named_parent = parent_layer_id
    if named_parent is None and isinstance(task_record, dict):
        configured_parent = task_record.get("working_parent_layer_id")
        if configured_parent is not None:
            named_parent = str(configured_parent)
    if named_parent is not None:
        for layer in candidates:
            if layer.get("layer_id") == named_parent:
                return layer
        raise ValueError("supervisor_parent_layer_missing")
    accepted = [layer for layer in candidates if layer.get("disposition") == "ACCEPTED_PARETO_PROGRESS"]
    if not accepted:
        raise ValueError("supervisor_no_accepted_parent_layer")
    if len(accepted) != 1:
        raise ValueError("supervisor_working_parent_must_be_named")
    return accepted[0]


def validate_authority(record: dict[str, Any], *, campaign_id: str, steps: int) -> dict[str, Any]:
    try:
        require_one_increment(steps, increment=INCREMENT)
    except ValueError as error:
        raise PermissionError(str(error)) from error
    if record.get("campaign_id") != campaign_id:
        raise PermissionError("supervisor_campaign_id_mismatch")
    if record.get("training_authorized") is not True or record.get("run_authorized") is not True:
        raise PermissionError("supervisor_training_or_run_authority_closed")
    if record.get("promotion_authorized") is not False or record.get("deployment_changed") is not False:
        raise PermissionError("supervisor_promotion_or_deployment_gate_invalid")
    scope = record.get("scope")
    if not isinstance(scope, dict) or int(scope.get("steps", -1)) != steps:
        raise PermissionError("supervisor_task_scope_steps_mismatch")
    return {
        "campaign_id": campaign_id,
        "training_authorized": True,
        "run_authorized": True,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_runtime_mutation": False,
    }


def validate_dry_run_authority(record: dict[str, Any], *, campaign_id: str, steps: int) -> dict[str, Any]:
    """Validate planning scope without opening training or run authority."""

    try:
        require_one_increment(steps, increment=INCREMENT)
    except ValueError as error:
        raise PermissionError(str(error)) from error
    if record.get("campaign_id") != campaign_id:
        raise PermissionError("supervisor_campaign_id_mismatch")
    if record.get("promotion_authorized") is not False or record.get("deployment_changed") is not False:
        raise PermissionError("supervisor_promotion_or_deployment_gate_invalid")
    scope = record.get("scope")
    if not isinstance(scope, dict) or int(scope.get("steps", -1)) != steps:
        raise PermissionError("supervisor_task_scope_steps_mismatch")
    return {
        "campaign_id": campaign_id,
        "training_authorized": record.get("training_authorized") is True,
        "run_authorized": record.get("run_authorized") is True,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_runtime_mutation": False,
        "planning_only": True,
    }


def build_command(trainer: Path, output_dir: Path, *, steps: int, extra_args: Sequence[str] = ()) -> list[str]:
    require_one_increment(steps, increment=INCREMENT)
    return [
        str(CANONICAL_PYTHON),
        str(trainer),
        "--authorize",
        "--steps",
        str(steps),
        "--output-dir",
        str(output_dir),
        *list(extra_args),
    ]


def classify_result(returncode: int, manifest: dict[str, Any] | None) -> str:
    if returncode != 0 or manifest is None:
        return "INCONCLUSIVE"
    if str(manifest.get("status", "")).startswith("HALTED"):
        return "INCONCLUSIVE"
    return "INCONCLUSIVE"


def manifest_parent_matches(manifest: dict[str, Any], parent: dict[str, Any]) -> bool:
    return _governor_parent_binding_matches(manifest, parent)


def run_supervised_increment(
    *,
    task_path: Path,
    ledger_path: Path,
    trainer: Path | None,
    output_dir: Path,
    campaign_id: str,
    steps: int = INCREMENT,
    parent_layer_id: str | None = None,
    hypothesis_id: str | None = None,
    execute: bool = False,
    operator_authorize: bool = False,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    timeout_seconds: int = 7200,
    extra_args: Sequence[str] = (),
    campaign_contract: Path | None = None,
) -> dict[str, Any]:
    task_record = load_task_record(task_path, campaign_id)
    ledger = _read_json(ledger_path)
    parent = select_parent_layer(ledger, parent_layer_id, task_record=task_record)
    authority = (
        validate_authority(task_record, campaign_id=campaign_id, steps=steps)
        if execute
        else validate_dry_run_authority(task_record, campaign_id=campaign_id, steps=steps)
    )
    if trainer is None:
        if campaign_contract is None:
            raise ValueError("supervisor_trainer_or_campaign_contract_required")
        trainer = DEFAULT_LAYER_ENGINE
        extra_args = ("--contract", str(campaign_contract), *tuple(extra_args))
    if not trainer.is_file():
        raise FileNotFoundError("supervisor_trainer_missing")
    if campaign_contract is not None and not campaign_contract.is_file():
        raise FileNotFoundError("supervisor_campaign_contract_missing")
    if output_dir.exists():
        raise FileExistsError("supervisor_output_directory_exists_refuse_overwrite")
    command = build_command(trainer, output_dir, steps=steps, extra_args=extra_args)
    plan = {
        "schema_version": "viv_slm_layered_supervisor_plan_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_id": campaign_id,
        "hypothesis_id": hypothesis_id or campaign_id,
        "strategy": STRATEGY,
        "advance_after": "preserve_layer_and_switch_hypothesis",
        "steps": steps,
        "parent_layer_id": parent.get("layer_id"),
        "working_parent_layer_id": task_record.get("working_parent_layer_id"),
        "behavior_reference_layer_id": task_record.get("behavior_reference_layer_id"),
        "parent_checkpoint": parent.get("checkpoint"),
        "parent_checkpoint_sha256": parent.get("checkpoint_sha256"),
        "command": command,
        "campaign_contract": str(campaign_contract).replace("\\", "/") if campaign_contract is not None else None,
        "authority": authority,
        "governor": {
            "module": "viv_slm_layer_governor",
            "schema_version": "viv_slm_layer_governor_v1",
            "side_effect_free_decisions": True,
        },
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_runtime_mutation": False,
        "execute_requested": execute,
    }
    if not execute:
        return {"status": "DRY_RUN_READY", "plan": plan}
    if not operator_authorize:
        raise PermissionError("supervisor_execute_requires_operator_authorize_flag")
    evidence_root.mkdir(parents=True, exist_ok=True)
    evidence_dir = evidence_root / f"{campaign_id}_{_utc_stamp()}"
    evidence_dir.mkdir(parents=False, exist_ok=False)
    (evidence_dir / "PLAN.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    completed = subprocess.run(
        command,
        cwd=str(VIV_ROOT),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    (evidence_dir / "stdout.log").write_text(completed.stdout or "", encoding="utf-8", newline="\n")
    (evidence_dir / "stderr.log").write_text(completed.stderr or "", encoding="utf-8", newline="\n")
    manifest_path = output_dir / "RUN_MANIFEST.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else None
    disposition = classify_result(completed.returncode, manifest)
    layer_record = None
    parent_binding_ok = manifest is not None and manifest_parent_matches(manifest, parent)
    if manifest is not None and not parent_binding_ok:
        disposition = "INCONCLUSIVE"
    if manifest is not None and (output_dir / "checkpoint.pt").is_file() and completed.returncode == 0:
        if not parent_binding_ok:
            completed = subprocess.CompletedProcess(command, 97, completed.stdout, "supervisor_parent_binding_mismatch")
        else:
            from register_viv_slm_checkpoint_layer import append_layer, make_layer_record

            layer_record = make_layer_record(
                layer_id=f"{campaign_id}_{_utc_stamp()}",
                checkpoint_path=output_dir / "checkpoint.pt",
                manifest_path=manifest_path,
                disposition=disposition,
                parent_checkpoint_path=Path(str(parent["checkpoint"]).replace("/", "\\")),
            )
            append_layer(ledger_path, layer_record)
    result = {
        "status": "SUPERVISOR_COMPLETED" if completed.returncode == 0 else "SUPERVISOR_TRAINER_FAILED",
        "returncode": completed.returncode,
        "disposition": disposition,
        "parent_binding_ok": parent_binding_ok,
        "evidence_dir": str(evidence_dir).replace("\\", "/"),
        "manifest": str(manifest_path).replace("\\", "/") if manifest is not None else None,
        "layer_record_sha256": layer_record.get("record_sha256") if layer_record else None,
        "authority": authority,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_runtime_mutation": False,
    }
    (evidence_dir / "RESULT.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--trainer", type=Path)
    parser.add_argument("--campaign-contract", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--parent-layer-id")
    parser.add_argument("--hypothesis-id")
    parser.add_argument("--steps", type=int, default=INCREMENT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--task", type=Path, default=CURRENT_TASK)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--operator-authorize", action="store_true")
    parser.add_argument("--extra-arg", action="append", default=[])
    args = parser.parse_args(argv)
    result = run_supervised_increment(
        task_path=args.task,
        ledger_path=args.ledger,
        trainer=args.trainer,
        output_dir=args.output_dir,
        campaign_id=args.campaign_id,
        steps=args.steps,
        parent_layer_id=args.parent_layer_id,
        hypothesis_id=args.hypothesis_id,
        execute=args.execute,
        operator_authorize=args.operator_authorize,
        evidence_root=args.evidence_root,
        timeout_seconds=args.timeout_seconds,
        extra_args=args.extra_arg,
        campaign_contract=args.campaign_contract,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
