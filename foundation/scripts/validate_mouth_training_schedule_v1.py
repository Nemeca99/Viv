#!/usr/bin/env python3
"""Validate a predeclared, closed-by-default overnight training schedule.

This module creates no authorization, opens no lease, and executes no task.
Each run must later receive its own named authorization and governed lease.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
DEFAULT_CAMPAIGN = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v3_campaign_v1"
MAX_RUNS = 8
MAX_LR = 1.0e-4


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path_outside_campaign:{path}") from exc
    return resolved


def validate_schedule(schedule: dict[str, Any], campaign_root: Path = DEFAULT_CAMPAIGN) -> dict[str, Any]:
    findings: list[str] = []
    if schedule.get("schema_version") != "mouth_training_schedule_v1":
        findings.append("schema_version")
    if schedule.get("status") != "SCHEDULE_READY_AUTH_CLOSED":
        findings.append("status_must_be_schedule_ready_auth_closed")
    if schedule.get("automatic_retry") is not False:
        findings.append("automatic_retry_must_be_false")
    if schedule.get("deployment_allowed") is not False:
        findings.append("deployment_allowed_must_be_false")
    declared_campaign = Path(str(schedule.get("campaign_root") or ""))
    if declared_campaign.resolve() != campaign_root.resolve():
        findings.append("campaign_root_mismatch")
    runs = schedule.get("runs")
    if not isinstance(runs, list) or not runs:
        findings.append("runs_must_be_nonempty_array")
        runs = []
    if len(runs) > MAX_RUNS:
        findings.append("run_count_exceeds_max")
    ids: set[str] = set()
    run_reports: list[dict[str, Any]] = []
    auth_root = campaign_root / "authorizations"
    for index, run in enumerate(runs):
        run_findings: list[str] = []
        if not isinstance(run, dict):
            findings.append(f"run_not_object:{index}")
            continue
        run_id = str(run.get("run_id") or "")
        if not run_id or run_id in ids:
            run_findings.append("run_id_missing_or_duplicate")
        ids.add(run_id)
        if not run_id.replace("_", "").replace("-", "").isalnum():
            run_findings.append("run_id_unsafe")
        try:
            lr = float(run["learning_rate"])
            if lr <= 0.0 or lr > MAX_LR:
                run_findings.append("learning_rate_out_of_bounds")
        except (KeyError, TypeError, ValueError):
            run_findings.append("learning_rate_invalid")
            lr = None
        steps = run.get("optimizer_steps")
        if not isinstance(steps, int) or isinstance(steps, bool) or steps <= 0:
            run_findings.append("optimizer_steps_invalid")
            steps = None
        checkpoints = run.get("checkpoint_steps")
        if not isinstance(checkpoints, list) or not checkpoints or any(not isinstance(item, int) or isinstance(item, bool) for item in checkpoints):
            run_findings.append("checkpoint_steps_invalid")
            checkpoints = []
        elif checkpoints != sorted(set(checkpoints)) or any(item <= 0 or (steps is not None and item > steps) for item in checkpoints):
            run_findings.append("checkpoint_steps_not_sorted_or_in_range")
        auth_raw = run.get("authorization_file")
        auth_path = None
        if not isinstance(auth_raw, str) or not auth_raw:
            run_findings.append("authorization_file_missing")
        else:
            try:
                auth_path = inside(Path(auth_raw), auth_root)
            except ValueError as exc:
                run_findings.append(str(exc))
        if not isinstance(run.get("parameter_note"), str) or not run["parameter_note"].strip():
            run_findings.append("parameter_note_missing")
        if run.get("automatic_retry") is not False:
            run_findings.append("run_automatic_retry_must_be_false")
        run_reports.append({"run_id": run_id, "learning_rate": lr, "optimizer_steps": steps, "checkpoint_steps": checkpoints, "authorization_file": str(auth_path).replace("\\", "/") if auth_path else None, "authorization_present": bool(auth_path and auth_path.is_file()), "findings": run_findings})
        findings.extend(f"{run_id or index}:{item}" for item in run_findings)
    return {"schema_version": "mouth_training_schedule_validation_v1", "status": "SCHEDULE_VALIDATION_PASS_AUTH_CLOSED" if not findings else "SCHEDULE_VALIDATION_FAIL", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "campaign_root": str(campaign_root).replace("\\", "/"), "schedule_sha256": None, "findings": findings, "runs": run_reports, "automatic_retry": False, "deployment_allowed": False, "training_executed": False, "leases_opened": 0, "authorization_changed": False, "next_action": "issue_one_named_authorization_per_run_before_execution" if not findings else "repair_schedule"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a closed governed training schedule")
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--campaign-root", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    schedule_path = args.schedule.resolve()
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    report = validate_schedule(schedule, args.campaign_root)
    report["schedule_sha256"] = sha256(schedule_path)
    report_path = args.report or (args.campaign_root / "SCHEDULE_VALIDATION.json")
    if report_path.exists():
        raise FileExistsError(f"refuse_to_overwrite:{report_path}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": report["status"] == "SCHEDULE_VALIDATION_PASS_AUTH_CLOSED", "status": report["status"], "runs": len(report["runs"]), "findings": report["findings"], "training_executed": False, "leases_opened": 0}, sort_keys=True))
    return 0 if report["status"] == "SCHEDULE_VALIDATION_PASS_AUTH_CLOSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
