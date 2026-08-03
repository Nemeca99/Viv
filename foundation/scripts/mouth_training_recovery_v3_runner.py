#!/usr/bin/env python3
"""Governed runner adapter for the closed V3 mouth recovery campaign.

The trainer remains in ``models/Training/code``.  This module only binds the
campaign contract to the existing Rust-backed ``training_security`` facade:
manifest validation happens first, security is required before mutation, and
exactly one ``TrainingLease`` owns the run.  Default execution is preflight;
the current campaign is intentionally unauthorized.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib import training_security  # noqa: E402
from models.Training.code import train_mouth_v3_targeted_patch as trainer  # noqa: E402
from scripts.execution_abort_report import write_abort_report  # noqa: E402

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
CAMPAIGN = TREE / "mouth_training_recovery_v3_campaign_v1"
PARENT = FOUNDATION / "models/Training/runs/openaster_stage1_gen_smoke_16_20260730T004859Z/adapter"
RUN_ROOT = FOUNDATION / "models/Training/runs/mouth_training_recovery_v3_campaign_v1"
STAGE_ID = "mouth_training_recovery_v3_campaign_v1"
OPTIMIZER_STEPS = 128
CHECKPOINT_STEPS = (32, 64, 96, 128)
GRADIENT_ACCUMULATION = 4
LEARNING_RATE = 1.0e-4
WARMUP_RATIO = 0.05
SEED = 42


def campaign_run_root(campaign_id: str) -> Path:
    return FOUNDATION / "models/Training/runs" / str(campaign_id)


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_manifest(root: Path = CAMPAIGN) -> dict[str, Any]:
    path = Path(root) / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"campaign_manifest_missing:{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_campaign(root: Path = CAMPAIGN, *, allow_authorized: bool = False) -> dict[str, Any]:
    """Validate all file locks without importing CUDA or opening a lease."""
    root = Path(root)
    manifest = load_manifest(root)
    findings: list[str] = []
    completed = manifest.get("status") == "CAMPAIGN_EXECUTION_COMPLETE"
    allowed_statuses = {"CAMPAIGN_ADMITTED_TRAINING_CLOSED", "ABORT_NO_PROMOTION", "CAMPAIGN_EXECUTION_COMPLETE"}
    if allow_authorized:
        allowed_statuses.add("CAMPAIGN_EXECUTION_AUTHORIZED")
    if manifest.get("status") not in allowed_statuses:
        findings.append("manifest_status")
    if not allow_authorized and not completed:
        for key in ("training_authorized", "run_authorized", "lora_authorized", "dpo_authorized"):
            if manifest.get(key) is not False:
                findings.append(f"{key}_must_be_false_until_authorized")
    elif not completed:
        if manifest.get("training_authorized") is not True or manifest.get("run_authorized") is not True:
            findings.append("execution_authorization_missing")
        for key in ("lora_authorized", "dpo_authorized"):
            if manifest.get(key) is not False:
                findings.append(f"{key}_must_remain_false")
    if completed:
        success_path = root / "EXECUTION_SUCCESS_REPORT.json"
        if not success_path.is_file():
            findings.append("execution_success_report_missing")
        adapter_path = Path()
        if success_path.is_file():
            try:
                success = json.loads(success_path.read_text(encoding="utf-8"))
                adapter_path = Path(str(success.get("adapter_final") or (success.get("training") or {}).get("adapter_final") or ""))
            except (OSError, json.JSONDecodeError):
                findings.append("execution_success_report_invalid")
        if manifest.get("lease_opened") is not True or manifest.get("gpu_steps") != OPTIMIZER_STEPS:
            findings.append("completed_execution_state")
        if not adapter_path.is_dir() or not (adapter_path / "adapter_model.safetensors").is_file():
            findings.append("committed_adapter_missing")
    elif manifest.get("lease_opened") is not False or manifest.get("gpu_steps") != 0:
        findings.append("manifest_execution_state")
    train_path = root / "train_256.jsonl"
    train = load_jsonl(train_path)
    if len(train) != 256:
        findings.append(f"train_count:{len(train)}")
    for row in train:
        if row.get("optimizer_eligible") is not True or row.get("response_only_loss_allowed") is not True:
            findings.append(f"train_contract:{row.get('pair_id')}")
            break
    source = manifest.get("source_train_candidate") or {}
    if source.get("sha256") != sha256(Path(str(source.get("path")))):
        findings.append("source_train_hash")
    if manifest.get("files", {}).get("train", {}).get("sha256") != sha256(train_path):
        findings.append("campaign_train_hash")
    parent = PARENT / "adapter_model.safetensors"
    if not parent.is_file():
        findings.append("parent_adapter_missing")
    report = {
        "schema_version": "mouth_training_recovery_v3_runner_validation_v1",
        "status": ("VALIDATION_PASS_EXECUTION_COMPLETE" if completed else "VALIDATION_PASS_AUTH_CLOSED") if not findings else "VALIDATION_FAIL",
        "recorded_utc": utc(),
        "campaign_root": str(root).replace("\\", "/"),
        "findings": findings,
        "train_rows": len(train),
        "train_sha256": sha256(train_path),
        "parent_adapter": str(PARENT).replace("\\", "/"),
        "parent_sha256": sha256(parent) if parent.is_file() else None,
        "training_authorized": manifest.get("training_authorized"),
        "run_authorized": manifest.get("run_authorized"),
        "lease_opened": bool(manifest.get("lease_opened")) if completed else False,
        "gpu_steps": int(manifest.get("gpu_steps") or 0) if completed else 0,
        "model_loaded": False,
    }
    if findings:
        raise ValueError(json.dumps(report, sort_keys=True))
    return report


def write_validation_report(root: Path = CAMPAIGN) -> dict[str, Any]:
    root = Path(root)
    report = validate_campaign(root)
    path = root / "RUNNER_VALIDATION.json"
    if path.exists():
        raise FileExistsError(f"refuse_to_overwrite:{path}")
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return report


def evaluate_generated_outputs(
    *,
    root: Path = CAMPAIGN,
    output_root: Path = RUN_ROOT,
    checkpoint_steps: tuple[int, ...] = CHECKPOINT_STEPS,
) -> dict[str, Any]:
    """Evaluate incumbent/checkpoints without opening a lease or training."""
    root = Path(root)
    validate_campaign(root)
    scripts = FOUNDATION / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from mouth_training_recovery_v3_generated_eval import evaluate_campaign

    plan = load_manifest(root)
    return evaluate_campaign(
        plan=plan,
        campaign_root=root,
        output_root=Path(output_root),
        checkpoint_steps=tuple(checkpoint_steps),
    )


def authorize_once(root: Path = CAMPAIGN, output_root: Path | None = None) -> dict[str, Any]:
    """Atomically authorize this named campaign after the closed preflight."""
    root = Path(root)
    manifest_path = root / "manifest.json"
    receipt_path = root / "V3_NAMED_AUTHORIZATION.json"
    manifest = load_manifest(root)
    campaign_id = str(manifest.get("campaign_id") or root.name)
    if manifest.get("status") != "CAMPAIGN_ADMITTED_TRAINING_CLOSED":
        raise ValueError("authorize_campaign_status_not_closed")
    if manifest.get("training_authorized") is not False or manifest.get("run_authorized") is not False:
        raise ValueError("authorize_campaign_already_open")
    if receipt_path.exists():
        raise FileExistsError(f"named_authorization_exists:{receipt_path}")
    preflight = None
    expected_train_sha = str((manifest.get("files", {}).get("train") or {}).get("sha256") or "")
    for candidate in sorted(root.glob("PREFLIGHT_READ_ONLY*.json")):
        try:
            candidate_report = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        actual_train_sha = str(((candidate_report.get("files") or {}).get("train") or {}).get("sha256_actual") or "")
        if candidate_report.get("status") == "PREFLIGHT_PASS_TRAINING_CLOSED" and actual_train_sha == expected_train_sha:
            preflight = candidate
    if preflight is None:
        raise ValueError("authorize_campaign_preflight_missing_failed_or_stale")
    target_output_root = Path(output_root) if output_root is not None else campaign_run_root(campaign_id)
    if target_output_root.exists():
        raise FileExistsError(f"authorize_campaign_output_exists:{target_output_root}")
    before = sha256(manifest_path)
    updated = dict(manifest)
    updated.update({
        "status": "CAMPAIGN_EXECUTION_AUTHORIZED",
        "training_authorized": True,
        "run_authorized": True,
        "authorization_scope": {"campaign_id": campaign_id, "learning_rate": LEARNING_RATE, "optimizer_steps": OPTIMIZER_STEPS, "checkpoint_steps": list(CHECKPOINT_STEPS), "promotion_authorized": False, "deployment_authorized": False},
        "next_action": "execute_named_campaign_once",
    })
    stage = manifest_path.with_name("manifest.authorize_stage.json")
    stage.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    try:
        stage.replace(manifest_path)
        receipt = {"schema_version": "v3_named_authorization_v1", "campaign_id": campaign_id, "manifest_before_sha256": before, "manifest_after_sha256": sha256(manifest_path), "preflight_path": str(preflight).replace("\\", "/"), "preflight_train_sha256": expected_train_sha, "training_authorized": True, "run_authorized": True, "optimizer_steps": OPTIMIZER_STEPS, "learning_rate": LEARNING_RATE, "checkpoint_steps": list(CHECKPOINT_STEPS), "promotion_authorized": False, "deployment_authorized": False, "recorded_utc": utc()}
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return receipt
    except Exception:
        manifest_path.write_bytes(json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))
        if receipt_path.exists():
            receipt_path.unlink()
        raise


def run_experiment(*, root: Path = CAMPAIGN, output_root: Path | None = None) -> dict[str, Any]:
    """Execute only after an external authorization flips the campaign open.

    This function is intentionally unreachable for the current manifest.  It
    performs no implicit authorization and never bypasses Rust-backed lease
    creation.
    """
    root = Path(root)
    manifest = load_manifest(root)
    campaign_id = str(manifest.get("campaign_id") or root.name)
    output_root = campaign_run_root(campaign_id) if output_root is None else Path(output_root)
    if manifest.get("run_authorized") is not True:
        raise PermissionError("run_authorized_false:separate_execution_authorization_required")
    if manifest.get("training_authorized") is not True:
        raise PermissionError("training_authorized_false:separate_execution_authorization_required")
    if manifest.get("lora_authorized") is not False or manifest.get("dpo_authorized") is not False:
        raise PermissionError("unapproved_training_mode_authorized")
    validation = validate_campaign(root, allow_authorized=True)
    training_security.require_training_security()

    train_path = root / "train_256.jsonl"
    parent_weights = PARENT / "adapter_model.safetensors"
    run_id = f"{campaign_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    request_manifest = sha256(root / "manifest.json")
    lease = None
    committed = False
    trained: dict[str, Any] | None = None
    commit: dict[str, Any] | None = None
    failure: BaseException | None = None
    quarantine_result: dict[str, Any] | None = None
    result: dict[str, Any] = {"ok": False, "run_id": run_id, "lease_opened": False, "gpu_steps": 0, "training_authorized": True, "run_authorized": True}
    try:
        lease = training_security.begin_run_lease(
            stage_id=campaign_id,
            run_id=run_id,
            manifest_sha256=request_manifest,
            source_hashes=(sha256(train_path), sha256(parent_weights)),
            max_duration_s=4 * 60 * 60,
            max_disk_mib=8192,
            lora_rank=16,
            sequence_cap=384,
        )
        result["lease_opened"] = True
        prepared = trainer.prepare_targeted_patch_runtime(
            train_jsonl=train_path,
            parent_adapter=PARENT,
            system_prompt="",
            learning_rate=LEARNING_RATE,
            gradient_accumulation=GRADIENT_ACCUMULATION,
            staging_root=Path(lease.staging_root),
            final_root=Path(lease.final_root),
            load_model=True,
            expected_rows=256,
            max_steps=OPTIMIZER_STEPS,
            warmup_ratio=WARMUP_RATIO,
        )
        trained = trainer.train_under_external_lease(
            lease=lease,
            prepared=prepared,
            max_steps=OPTIMIZER_STEPS,
            checkpoint_steps=CHECKPOINT_STEPS,
            gradient_accumulation=GRADIENT_ACCUMULATION,
            seed=SEED,
            commit=False,
        )
        if not trained.get("ok"):
            raise RuntimeError(f"training_failed:{trained}")
        commit = lease.commit()
        if not commit.get("allowed"):
            raise PermissionError(f"security_commit_denied:{commit}")
        committed = True
        result.update({"ok": True, "gpu_steps": OPTIMIZER_STEPS, "training": trained, "security_commit": commit, "validation": validation})
        success_receipt = {
            "schema_version": "execution_success_report_v1",
            "recorded_utc": utc(),
            "campaign_id": campaign_id,
            "run_id": run_id,
            "status": "EXECUTION_COMMITTED_NO_PROMOTION",
            "authority": {
                "training_authorized": True,
                "run_authorized": True,
                "promotion_authorized": False,
                "deployment_authorized": False,
            },
            "gpu_steps": OPTIMIZER_STEPS,
            "lease_opened": True,
            "promotion_allowed": False,
            "deployment_changed": False,
            "adapter_final": trained.get("adapter_final"),
            "adapter_staging": trained.get("adapter_staging"),
            "training": trained,
            "security_commit": commit,
            "validation": validation,
        }
        success_path = root / "EXECUTION_SUCCESS_REPORT.json"
        if success_path.exists():
            raise FileExistsError(f"refuse_overwrite:{success_path}")
        success_path.write_text(
            json.dumps(success_receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        manifest_path = root / "manifest.json"
        manifest = load_manifest(root)
        manifest.update({
            "status": "CAMPAIGN_EXECUTION_COMPLETE",
            "gpu_steps": OPTIMIZER_STEPS,
            "lease_opened": True,
            "next_action": "read_only_generation_validation_then_separate_promotion_review",
            "execution_success_report": str(success_path).replace("\\", "/"),
        })
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        output_root.mkdir(parents=True, exist_ok=True)
        source_root = Path(lease.final_root)
        for step in CHECKPOINT_STEPS:
            source = source_root / f"adapter_step_{step}"
            target = Path(output_root) / f"adapter_step_{step}"
            if source.is_dir() and not target.exists():
                shutil.copytree(source, target)
        return result
    except BaseException as exc:
        failure = exc
        raise
    finally:
        if lease is not None and not committed:
            try:
                quarantine_result = lease.quarantine("runner_abort", f"v3_runner_aborted_before_commit:{type(failure).__name__ if failure else 'unknown'}")
            except Exception:
                quarantine_result = {"allowed": False, "error": traceback.format_exc()}
            if failure is not None:
                try:
                    write_abort_report(
                        root / "EXECUTION_ABORT_REPORT.json",
                        campaign_id=campaign_id,
                        run_id=run_id,
                        stage="run_experiment",
                        exception_type=type(failure).__name__,
                        exception_message=str(failure),
                        traceback_text="".join(traceback.format_exception(failure)),
                        trained_result=trained,
                        commit_verdict=commit,
                        quarantine_root=str((quarantine_result or {}).get("path") or (quarantine_result or {}).get("quarantine_root") or "") or None,
                        authority={"training_authorized": True, "run_authorized": True, "lease_opened": True, "promotion_authorized": False, "deployment_authorized": False},
                    )
                except Exception:
                    pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="V3 governed runner; default is read-only validation")
    parser.add_argument("--validate", action="store_true", help="write the closed validation receipt")
    parser.add_argument("--execute", action="store_true", help="execute only after external authorization")
    parser.add_argument("--campaign-root", type=Path, default=CAMPAIGN, help="campaign directory; defaults to the historical V1 path")
    parser.add_argument("--output-root", type=Path, default=None, help="optional run output directory")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(run_experiment(root=args.campaign_root, output_root=args.output_root), indent=2, sort_keys=True))
    else:
        report = write_validation_report(args.campaign_root) if args.validate else validate_campaign(args.campaign_root)
        print(json.dumps({"ok": True, "status": report["status"], "findings": report["findings"], "training_authorized": False, "run_authorized": False, "gpu_steps": 0}, sort_keys=True))
