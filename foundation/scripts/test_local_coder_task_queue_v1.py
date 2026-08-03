#!/usr/bin/env python3
"""Standard-library tests for the local coder queue safety and logging contract."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from local_coder_task_queue_v1 import MAX_TASKS, QueueInterrupted, expand_artifact_root, run_queue, validate_draft_prompt, validate_draft_response, verify_log_chain  # noqa: E402
from local_coder_tool_registry_v1 import list_tools  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="local-coder-queue-") as raw:
        root = Path(raw)
        artifact = root / "artifacts"
        artifact.mkdir()
        checked = artifact / "checked.json"
        checked.write_text(json.dumps({"status": "READY"}) + "\n", encoding="utf-8")
        tasks = artifact / "tasks.json"
        tasks.write_text(json.dumps([
            {"task_id": "check", "kind": "read_only_check", "path": str(checked), "json_status": "READY"},
            {"task_id": "skip", "kind": "read_only_check", "path": str(checked), "if_previous_status": "error"},
        ]), encoding="utf-8")
        summary = run_queue(tasks, artifact, secure_writes=False)
        assert summary["status"] == "QUEUE_PASS"
        assert [row["status"] for row in summary["tasks"]] == ["success", "skipped_condition"]
        assert summary["retries"] == 0
        assert summary["shell_execution"] is False
        assert summary["training"] is False
        assert summary["integration_allowed"] is False
        assert summary["audit_chain_verified"] is True
        assert verify_log_chain(artifact / "queue_log.jsonl") is True
        tampered_log = artifact / "tampered_queue_log.jsonl"
        tampered_log.write_text((artifact / "queue_log.jsonl").read_text(encoding="utf-8").replace("task_start", "task_start_tampered", 1), encoding="utf-8")
        assert verify_log_chain(tampered_log) is False
        assert len((artifact / "queue_log.jsonl").read_text(encoding="utf-8").splitlines()) == 4
        bad_artifacts = artifact / "bad-artifacts"
        bad_artifacts.mkdir()
        bad = bad_artifacts / "bad.json"
        bad.write_text(json.dumps([{"task_id": "bad", "kind": "train"}]), encoding="utf-8")
        try:
            run_queue(bad, bad_artifacts, secure_writes=False)
        except ValueError as exc:
            assert "task_kind_denied" in str(exc)
        else:
            raise AssertionError("forbidden_task_kind_not_refused")
        duplicate_root = artifact / "duplicate-artifacts"
        duplicate_root.mkdir()
        duplicate_tasks = duplicate_root / "duplicate.json"
        duplicate_tasks.write_text(json.dumps([
            {"task_id": "same", "kind": "read_only_check", "path": str(checked)},
            {"task_id": "same", "kind": "read_only_check", "path": str(checked)},
        ]), encoding="utf-8")
        try:
            run_queue(duplicate_tasks, duplicate_root, secure_writes=False)
        except ValueError as exc:
            assert "task_id_duplicate" in str(exc)
        else:
            raise AssertionError("duplicate_task_id_not_refused")
        failure_artifacts = artifact / "failure-artifacts"
        failure_artifacts.mkdir()
        fail_tasks = failure_artifacts / "fail_tasks.json"
        fail_tasks.write_text(json.dumps([
            {"task_id": "missing", "kind": "read_only_check", "path": str(artifact / "missing.json")},
            {"task_id": "must_stop", "kind": "read_only_check", "path": str(checked)},
            {"task_id": "conditional", "kind": "read_only_check", "path": str(checked), "if_previous_status": "error"},
        ]), encoding="utf-8")
        failed = run_queue(fail_tasks, failure_artifacts, secure_writes=False)
        assert failed["status"] == "QUEUE_FAIL"
        assert [row["status"] for row in failed["tasks"]] == ["error", "skipped_after_failure", "skipped_condition"]
        assert failed["downstream_after_failure"] is True
        too_many_root = artifact / "too-many-artifacts"
        too_many_root.mkdir()
        too_many = too_many_root / "too_many.json"
        too_many.write_text(json.dumps([{"task_id": str(i), "kind": "read_only_check", "path": str(checked)} for i in range(MAX_TASKS + 1)]), encoding="utf-8")
        try:
            run_queue(too_many, too_many_root, secure_writes=False)
        except ValueError as exc:
            assert "task_count_exceeds_max" in str(exc)
        else:
            raise AssertionError("task_count_cap_not_enforced")
        prompt_guard_root = artifact / "prompt-guard-artifacts"
        prompt_guard_root.mkdir()
        prompt_guard = prompt_guard_root / "prompt_guard.json"
        prompt_guard.write_text(json.dumps([{
            "task_id": "blocked",
            "kind": "draft_code",
            "prompt": "Run a training run and deploy the adapter.",
        }]), encoding="utf-8")
        blocked = run_queue(prompt_guard, prompt_guard_root, secure_writes=False)
        assert blocked["status"] == "QUEUE_FAIL"
        assert blocked["tasks"][0]["status"] == "error"
        assert "draft_prompt_privileged_request" in blocked["tasks"][0]["exception"]
        validate_draft_prompt("Do not run training, open a lease, or deploy anything; draft a validator only.")
        expanded = expand_artifact_root({"root": "${ARTIFACT_ROOT}/nested", "items": ["${ARTIFACT_ROOT}/a"]}, artifact)
        assert expanded["root"].startswith(str(artifact).replace("\\", "/"))
        assert expanded["items"][0].startswith(str(artifact).replace("\\", "/"))
        validate_draft_response("def validate_schedule(schedule):\n    return checkpoint_steps\n", {"required_markers": ["checkpoint_steps"], "forbidden_markers": ["subprocess"]})
        try:
            validate_draft_response("def f():\n    return 1\n", {"required_markers": ["checkpoint_steps"]})
        except ValueError as exc:
            assert "draft_required_marker_missing" in str(exc)
        else:
            raise AssertionError("missing_output_marker_not_refused")
        occupied_root = artifact / "occupied-artifacts"
        occupied_root.mkdir()
        (occupied_root / "queue_log.jsonl").write_text("prior\n", encoding="utf-8")
        occupied_tasks = occupied_root / "tasks.json"
        occupied_tasks.write_text(json.dumps([{"task_id": "check", "kind": "read_only_check", "path": str(checked)}]), encoding="utf-8")
        try:
            run_queue(occupied_tasks, occupied_root, secure_writes=False)
        except FileExistsError as exc:
            assert "refuse_to_append_existing_queue_log" in str(exc)
        else:
            raise AssertionError("existing_queue_log_not_refused")
        recovery_root = artifact / "recovery-artifacts"
        recovery_root.mkdir()
        recovery_checked = recovery_root / "checked.json"
        recovery_checked.write_text(json.dumps({"status": "READY"}) + "\n", encoding="utf-8")
        recovery_tasks = recovery_root / "recovery_tasks.json"
        recovery_tasks.write_text(json.dumps([
            {"task_id": "first", "kind": "read_only_check", "path": str(recovery_checked)},
            {"task_id": "second", "kind": "read_only_check", "path": str(recovery_checked)},
        ]), encoding="utf-8")
        try:
            run_queue(recovery_tasks, recovery_root, secure_writes=False, stop_after_tasks=1)
        except QueueInterrupted as exc:
            assert "queue_interrupted_after:1" in str(exc)
        else:
            raise AssertionError("interrupt_did_not_persist")
        resumed = run_queue(recovery_tasks, recovery_root, secure_writes=False, resume=True)
        assert resumed["status"] == "QUEUE_PASS"
        assert resumed["audit_chain_verified"] is True
        assert [row["status"] for row in resumed["tasks"]] == ["success", "success"]
        assert json.loads((recovery_root / "queue_state.json").read_text(encoding="utf-8"))["status"] == "COMPLETED"
        dry_root = artifact / "dry-run-artifacts"
        dry_root.mkdir()
        dry_tasks = dry_root / "dry_tasks.json"
        dry_tasks.write_text(json.dumps([{
            "task_id": "mutation-preview",
            "kind": "prebuilt_tool",
            "tool": "normalize_artifact",
            "args": {"path": str(checked), "output_name": "would_not_be_written.json"},
        }]), encoding="utf-8")
        dry = run_queue(dry_tasks, dry_root, secure_writes=False, mode="dry_run")
        assert dry["status"] == "QUEUE_PASS"
        assert dry["tasks"][0]["status"] == "dry_run_would_execute"
        assert dry["mutation_performed"] is False
        assert not (checked.parent / "would_not_be_written.json").exists()
        live_root = artifact / "approval-artifacts"
        live_root.mkdir()
        live_tasks = live_root / "live_tasks.json"
        live_tasks.write_text(dry_tasks.read_text(encoding="utf-8"), encoding="utf-8")
        denied = run_queue(live_tasks, live_root, secure_writes=False, mode="live")
        assert denied["status"] == "QUEUE_FAIL"
        assert denied["audit_chain_verified"] is True
        assert "mutation_requires_run_and_task_operator_approval" in denied["tasks"][0]["exception"]
        mismatch_root = artifact / "mismatch-artifacts"
        mismatch_root.mkdir()
        mismatch_tasks = mismatch_root / "mismatch_tasks.json"
        mismatch_tasks.write_text(recovery_tasks.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            run_queue(mismatch_tasks, mismatch_root, secure_writes=False, stop_after_tasks=1)
        except QueueInterrupted:
            pass
        try:
            run_queue(mismatch_tasks, mismatch_root, secure_writes=False, mode="live", resume=True)
        except ValueError as exc:
            assert "resume_mode_mismatch" in str(exc)
        else:
            raise AssertionError("resume_mode_mismatch_not_refused")
    tools = list_tools()
    assert any(item["name"] == "normalize_artifact" and item["mutating"] is True for item in tools)
    assert any(item["name"] == "sandbox_state" and item["mutating"] is False for item in tools)
    assert any(item["name"] == "sandbox_verify_stage" and item["mutating"] is False for item in tools)
    assert all(item["name"] != "run" for item in tools)
    print("ok: queue logging, condition gate, no-retry, and forbidden-kind refusal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
