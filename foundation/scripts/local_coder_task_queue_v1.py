#!/usr/bin/env python3
"""Logged, artifact-only task queue for the local Python coder.

The queue can ask Ollama for untrusted code drafts or perform bounded
read-only artifact checks. It never executes model output, shell commands,
training, leases, authorization, deployment, or repository writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

MODEL = "nerdsking-python-coder-3b-i:latest"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
ALLOWED_READ_ROOTS = (Path(r"L:/Continue/Viv/foundation"),)
FORBIDDEN_TASK_KINDS = {"run", "train", "deploy", "authorize", "lease"}
MAX_TASKS = 32
MAX_PROMPT_CHARS = 20000
MAX_DRAFT_BYTES = 1_000_000
MAX_TIMEOUT_S = 600.0
MAX_OUTPUT_MARKERS = 32
MAX_OUTPUT_MARKER_CHARS = 256
QUEUE_MODES = {"dry_run", "live"}
CAPABILITY_MANIFEST_PATH = Path(__file__).with_name("local_coder_capability_manifest_v1.json")
CURRENT_TASK_PATH = FOUNDATION / "artifacts" / "auto" / "agentic" / "CURRENT_TASK.json"
CODER_CONTRACT = (
    "You are an untrusted local drafting worker for an AIOS foreman. "
    "Return only the requested draft. Do not execute tools, commands, training, "
    "leases, authorization, deployment, or repository writes. Do not claim that "
    "anything was tested or verified. Use only standard Python unless the prompt "
    "explicitly says otherwise. The foreman will review your output.\n\n"
)

FORBIDDEN_DRAFT_PROMPT_PATTERNS = (
    r"\b(?:execute|run|launch|start)\s+(?:a\s+)?(?:training|train(?:ing)?\s+run)\b",
    r"\b(?:open|begin|commit)\s+(?:a\s+)?run\s+lease\b",
    r"\b(?:authorize|issue|consume)\s+(?:a\s+)?(?:run|training)\s+(?:token|authorization)?\b",
    r"\b(?:execute|run)\s+(?:a\s+)?(?:shell|powershell|cmd|subprocess)\b",
    r"\b(?:deploy|promote)\s+(?:the\s+)?(?:adapter|model|build)\b",
)


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_draft_prompt(prompt: str) -> None:
    for pattern in FORBIDDEN_DRAFT_PROMPT_PATTERNS:
        for match in re.finditer(pattern, prompt, flags=re.IGNORECASE):
            prefix = prompt[max(0, match.start() - 48):match.start()]
            if re.search(r"(?:do\s+not|must\s+not|never|without)\s+(?:\w+\s+){0,4}$", prefix, flags=re.IGNORECASE):
                continue
            raise ValueError(f"draft_prompt_privileged_request:{pattern}")


def expand_artifact_root(value: Any, artifact_root: Path) -> Any:
    """Expand only the fixed queue artifact-root token in tool arguments."""
    if isinstance(value, str):
        return value.replace("${ARTIFACT_ROOT}", str(artifact_root).replace("\\", "/"))
    if isinstance(value, list):
        return [expand_artifact_root(item, artifact_root) for item in value]
    if isinstance(value, dict):
        return {key: expand_artifact_root(item, artifact_root) for key, item in value.items()}
    return value


def validate_draft_response(response: str, task: dict[str, Any]) -> None:
    required = task.get("required_markers") or []
    forbidden = task.get("forbidden_markers") or []
    if not isinstance(required, list) or not isinstance(forbidden, list):
        raise ValueError("draft_output_markers_must_be_lists")
    if len(required) > MAX_OUTPUT_MARKERS or len(forbidden) > MAX_OUTPUT_MARKERS:
        raise ValueError(f"draft_output_marker_count_exceeds_max:{MAX_OUTPUT_MARKERS}")
    for label, markers in (("required", required), ("forbidden", forbidden)):
        for marker in markers:
            if not isinstance(marker, str) or not marker or len(marker) > MAX_OUTPUT_MARKER_CHARS:
                raise ValueError(f"draft_{label}_marker_invalid")
            present = marker in response
            if label == "required" and not present:
                raise ValueError(f"draft_required_marker_missing:{marker}")
            if label == "forbidden" and present:
                raise ValueError(f"draft_forbidden_marker_present:{marker}")


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_inside(path: Path, roots: tuple[Path, ...]) -> Path:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return resolved
        except ValueError:
            continue
    raise ValueError(f"path_outside_allowed_roots:{path}")


def _security_context() -> tuple[Any, float]:
    from lib.master_rid import load_master_rid
    from lib.security_membrane import require_membrane

    missing = require_membrane()
    if missing is not None:
        raise PermissionError(f"security_membrane:{missing.get('reason')}")
    return __import__("lib.security_membrane", fromlist=["tool_gate"]).tool_gate, float(load_master_rid().master_s_n)


def write_text(path: Path, content: str, security: tuple[Any, float] | None) -> None:
    if security is not None:
        tool_gate, s_n = security
        verdict = tool_gate("write_file", {"path": str(path).replace("\\", "/"), "content": content}, s_n)
        if not verdict.get("allowed"):
            raise PermissionError(f"tool_gate_denied:{verdict}")
    path.write_text(content, encoding="utf-8", newline="\n")


def append_log(path: Path, row: dict[str, Any], security: tuple[Any, float] | None) -> None:
    prior = path.read_text(encoding="utf-8") if path.exists() else ""
    chained = dict(row)
    chained["previous_log_sha256"] = digest_text(prior) if prior else None
    chained["event_sha256"] = digest_text(json.dumps(chained, sort_keys=True, ensure_ascii=False))
    write_text(path, prior + json.dumps(chained, sort_keys=True, ensure_ascii=False) + "\n", security)


def verify_log_chain(path: Path) -> bool:
    prior = ""
    for raw in path.read_text(encoding="utf-8").splitlines(True):
        row = json.loads(raw)
        event_sha = row.pop("event_sha256", None)
        expected_previous = digest_text(prior) if prior else None
        if row.get("previous_log_sha256") != expected_previous:
            return False
        if not event_sha or digest_text(json.dumps(row, sort_keys=True, ensure_ascii=False)) != event_sha:
            return False
        prior += raw
    return True


def rollback_mutations(results: list[dict[str, Any]], security: tuple[Any, float] | None) -> list[dict[str, Any]]:
    """Remove only new queue outputs after a failed transaction, fail-closed."""
    rows: list[dict[str, Any]] = []
    for result in reversed(results):
        if not result.get("mutation_performed"):
            continue
        detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
        tool_result = detail.get("result") if isinstance(detail.get("result"), dict) else {}
        raw_path = result.get("output_path") or tool_result.get("output")
        if not raw_path:
            rows.append({"task_id": result.get("task_id"), "status": "rollback_unavailable", "reason": "mutation_output_path_missing"})
            continue
        path = Path(str(raw_path)).resolve()
        try:
            path.relative_to(FOUNDATION / "artifacts")
        except ValueError:
            rows.append({"task_id": result.get("task_id"), "path": str(path).replace("\\", "/"), "status": "rollback_refused", "reason": "target_outside_artifacts"})
            continue
        if not path.is_file():
            rows.append({"task_id": result.get("task_id"), "path": str(path).replace("\\", "/"), "status": "rollback_verified", "reason": "target_already_absent"})
            continue
        try:
            if security is not None:
                tool_gate, s_n = security
                verdict = tool_gate("delete_file", {"path": str(path).replace("\\", "/")}, s_n)
                if not verdict.get("allowed"):
                    raise PermissionError(f"tool_gate_denied:{verdict}")
            path.unlink()
            verified = not path.exists()
            rows.append({"task_id": result.get("task_id"), "path": str(path).replace("\\", "/"), "status": "rollback_verified" if verified else "rollback_failed"})
        except Exception as exc:  # noqa: BLE001
            rows.append({"task_id": result.get("task_id"), "path": str(path).replace("\\", "/"), "status": "rollback_failed", "exception": f"{type(exc).__name__}:{exc}"})
    return rows


def call_coder(prompt: str, *, timeout_s: float) -> str:
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "seed": 42, "num_ctx": 8192},
    }).encode("utf-8")
    request = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        body = json.loads(response.read().decode("utf-8"))
    result = str(body.get("response") or "").strip()
    if not result:
        raise ValueError("local_coder_empty_response")
    return result


def run_read_only_check(task: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    target = resolve_inside(Path(str(task["path"])), ALLOWED_READ_ROOTS + (artifact_root,))
    if not target.is_file():
        raise FileNotFoundError(f"read_only_target_missing:{target}")
    result: dict[str, Any] = {"path": str(target).replace("\\", "/"), "sha256": digest_file(target), "bytes": target.stat().st_size}
    if task.get("json_status") is not None:
        data = json.loads(target.read_text(encoding="utf-8"))
        observed = data.get("status") if isinstance(data, dict) else None
        result["json_status"] = observed
        if observed != task["json_status"]:
            raise ValueError(f"json_status_mismatch:expected={task['json_status']};got={observed}")
    return result


class QueueInterrupted(RuntimeError):
    """Deliberate test/operator interruption after a durable task checkpoint."""


def task_is_mutating(task: dict[str, Any]) -> bool:
    kind = str(task.get("kind") or "")
    if kind == "draft_code":
        return True
    if kind == "prebuilt_tool":
        from local_coder_tool_registry_v1 import TOOLS

        entry = TOOLS.get(str(task.get("tool") or ""))
        return bool(entry and entry[2])
    return False


def persist_queue_state(path: Path, state: dict[str, Any], security: tuple[Any, float] | None) -> None:
    write_text(path, json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n", security)


def load_capability_manifest() -> dict[str, Any]:
    manifest = json.loads(CAPABILITY_MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "local_coder_capability_manifest_v1":
        raise ValueError("capability_manifest_schema_invalid")
    if manifest.get("local_only") is not True or manifest.get("network") is not False or manifest.get("shell") is not False:
        raise ValueError("capability_manifest_boundary_invalid")
    return manifest


def write_pending_approval(
    artifact_root: Path,
    *,
    trace_id: str,
    task: dict[str, Any],
    task_list_sha256: str,
    mode: str,
    reason: str,
    security: tuple[Any, float] | None,
) -> None:
    receipt = {
        "schema_version": "local_coder_pending_approval_v1",
        "status": "PENDING_APPROVAL",
        "trace_id": trace_id,
        "task_id": str(task.get("task_id") or ""),
        "task_kind": str(task.get("kind") or ""),
        "tool": task.get("tool"),
        "task_list_sha256": task_list_sha256,
        "mode": mode,
        "reason": reason,
        "operator_approval_required": True,
        "created_utc": utc(),
    }
    path = artifact_root / "pending_approval.json"
    if not path.exists():
        write_text(path, json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n", security)


def update_current_task(
    *,
    status: str,
    trace_id: str,
    task_list_path: Path,
    task_list_sha256: str,
    artifact_root: Path,
    mode: str,
    current_index: int,
    total_tasks: int,
    next_action: str,
    last_task: dict[str, Any] | None,
    security: tuple[Any, float] | None,
) -> None:
    if security is None:
        return
    prior: dict[str, Any] = {}
    if CURRENT_TASK_PATH.is_file():
        try:
            prior = json.loads(CURRENT_TASK_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prior = {}
    active_trace = str(prior.get("trace_id") or "")
    if status == "IN_PROGRESS" and prior.get("status") == "IN_PROGRESS" and active_trace and active_trace != trace_id:
        raise RuntimeError(f"current_task_already_active:{active_trace}")
    record = {
        "schema_version": "viv_current_task_v1",
        "status": status,
        "objective": f"Execute bounded local-coder task list {task_list_path.name}",
        "phase": "local_coder_queue",
        "trace_id": trace_id,
        "task_list": str(task_list_path).replace("\\", "/"),
        "task_list_sha256": task_list_sha256,
        "artifact_root": str(artifact_root).replace("\\", "/"),
        "mode": mode,
        "authority": {"training": False, "lease_opened": False, "authorization_changed": False, "deployment_changed": False},
        "current_index": current_index,
        "total_tasks": total_tasks,
        "last_task": last_task,
        "next_action": next_action,
        "updated_utc": utc(),
    }
    if prior.get("started_utc") and prior.get("trace_id") == trace_id:
        record["started_utc"] = prior["started_utc"]
    else:
        record["started_utc"] = utc()
    write_text(CURRENT_TASK_PATH, json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n", security)


def verify_post_action(result: dict[str, Any]) -> bool | None:
    status = result.get("status")
    if status in {"skipped_condition", "skipped_after_failure"}:
        return None
    if status != "success":
        return False
    if not result.get("mutation_performed"):
        return True
    detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
    tool_result = detail.get("result") if isinstance(detail.get("result"), dict) else {}
    output_path = result.get("output_path") or tool_result.get("output")
    expected_sha = result.get("response_sha256") or tool_result.get("output_sha256")
    if not output_path or not expected_sha:
        return False
    path = Path(str(output_path))
    return path.is_file() and digest_file(path).lower() == str(expected_sha).lower()


def run_queue(
    task_list_path: Path,
    artifact_root: Path,
    *,
    secure_writes: bool = True,
    mode: str = "dry_run",
    operator_approved: bool = False,
    resume: bool = False,
    stop_after_tasks: int | None = None,
) -> dict[str, Any]:
    if mode not in QUEUE_MODES:
        raise ValueError(f"queue_mode_denied:{mode}")
    if stop_after_tasks is not None and stop_after_tasks <= 0:
        raise ValueError("stop_after_tasks_must_be_positive")
    task_list_path = resolve_inside(Path(task_list_path), ALLOWED_READ_ROOTS + (artifact_root,))
    artifact_root = Path(artifact_root).resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    security = _security_context() if secure_writes else None
    capability_manifest = load_capability_manifest()
    log_path = artifact_root / "queue_log.jsonl"
    summary_path = artifact_root / "queue_summary.json"
    state_path = artifact_root / "queue_state.json"
    if summary_path.exists():
        raise FileExistsError(f"refuse_to_overwrite:{summary_path}")
    tasks = json.loads(task_list_path.read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise ValueError("task_list_must_be_array")
    if len(tasks) > MAX_TASKS:
        raise ValueError(f"task_count_exceeds_max:{len(tasks)}:{MAX_TASKS}")
    task_list_sha256 = digest_file(task_list_path)
    trace_id = uuid.uuid4().hex
    if resume:
        if not state_path.is_file() or not log_path.is_file():
            raise FileNotFoundError("resume_state_or_log_missing")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("task_list_sha256") != task_list_sha256:
            raise ValueError("resume_task_list_hash_mismatch")
        if state.get("mode") != mode:
            raise ValueError("resume_mode_mismatch")
        if bool(state.get("operator_approved")) != bool(operator_approved):
            raise ValueError("resume_operator_approval_mismatch")
        results = list(state.get("results") or [])
        trace_id = str(state.get("trace_id") or trace_id)
        previous_status = state.get("previous_status")
        start_index = len(results)
    else:
        if log_path.exists():
            raise FileExistsError(f"refuse_to_append_existing_queue_log:{log_path}")
        if state_path.exists():
            raise FileExistsError(f"refuse_to_overwrite:{state_path}")
        previous_status = None
        results = []
        start_index = 0
        state = {
            "schema_version": "local_coder_task_queue_state_v1",
            "status": "RUNNING",
            "task_list_sha256": task_list_sha256,
            "mode": mode,
            "operator_approved": bool(operator_approved),
            "trace_id": trace_id,
            "next_index": 0,
            "previous_status": None,
            "results": [],
        }
        persist_queue_state(state_path, state, security)
    update_current_task(status="IN_PROGRESS", trace_id=trace_id, task_list_path=task_list_path, task_list_sha256=task_list_sha256, artifact_root=artifact_root, mode=mode, current_index=start_index, total_tasks=len(tasks), next_action="execute_next_task", last_task=results[-1] if results else None, security=security)
    task_ids: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError(f"task_not_object:{index}")
        task_id = str(task.get("task_id") or f"task-{index:03d}")
        if not task_id.strip():
            raise ValueError(f"task_id_empty:{index}")
        if task_id in task_ids:
            raise ValueError(f"task_id_duplicate:{task_id}")
        task_ids.add(task_id)
        if index < start_index:
            continue
        kind = str(task.get("kind") or "")
        if kind in FORBIDDEN_TASK_KINDS or kind not in {"draft_code", "read_only_check", "prebuilt_tool"}:
            raise ValueError(f"task_kind_denied:{task_id}:{kind}")
        condition = task.get("if_previous_status")
        start = utc()
        span_id = uuid.uuid4().hex
        base = {"task_id": task_id, "index": index, "kind": kind, "model": MODEL if kind == "draft_code" else None, "tool": task.get("tool") if kind == "prebuilt_tool" else None, "started_utc": start, "trace_id": trace_id, "span_id": span_id}
        append_log(log_path, {"event": "task_start", **base, "previous_status": previous_status, "if_previous_status": condition}, security)
        if previous_status in {"error", "tool_fail"} and condition is None:
            result = {**base, "status": "skipped_after_failure", "finished_utc": utc(), "previous_status": previous_status, "skip_reason": "explicit_if_previous_status_required_after_failure"}
            append_log(log_path, {"event": "task_end", **result}, security)
            results.append(result)
            previous_status = result["status"]
            state.update({"next_index": index + 1, "previous_status": previous_status, "results": results})
            persist_queue_state(state_path, state, security)
            update_current_task(status="IN_PROGRESS", trace_id=trace_id, task_list_path=task_list_path, task_list_sha256=task_list_sha256, artifact_root=artifact_root, mode=mode, current_index=index + 1, total_tasks=len(tasks), next_action="halt_after_failure", last_task=result, security=security)
            continue
        if condition is not None and condition != previous_status:
            result = {**base, "status": "skipped_condition", "finished_utc": utc(), "previous_status": previous_status}
            append_log(log_path, {"event": "task_end", **result}, security)
            results.append(result)
            previous_status = result["status"]
            state.update({"next_index": index + 1, "previous_status": previous_status, "results": results})
            persist_queue_state(state_path, state, security)
            continue
        draft_evidence: dict[str, Any] = {}
        try:
            if task_is_mutating(task) and mode == "dry_run":
                if kind == "draft_code":
                    preview_prompt = str(task.get("prompt") or "")
                    if not preview_prompt.strip():
                        raise ValueError("draft_prompt_empty")
                    if len(preview_prompt) > MAX_PROMPT_CHARS:
                        raise ValueError(f"draft_prompt_exceeds_max:{len(preview_prompt)}:{MAX_PROMPT_CHARS}")
                    validate_draft_prompt(preview_prompt)
                result = {**base, "status": "dry_run_would_execute", "finished_utc": utc(), "mutation_performed": False, "operator_approval_required": True}
                write_pending_approval(artifact_root, trace_id=trace_id, task=task, task_list_sha256=task_list_sha256, mode=mode, reason="dry_run_mutation_preview", security=security)
            elif task_is_mutating(task) and (not operator_approved or task.get("operator_approved") is not True):
                write_pending_approval(artifact_root, trace_id=trace_id, task=task, task_list_sha256=task_list_sha256, mode=mode, reason="run_and_task_operator_approval_required", security=security)
                raise PermissionError("mutation_requires_run_and_task_operator_approval")
            elif kind == "read_only_check":
                read_task = dict(task)
                read_task["path"] = expand_artifact_root(str(task.get("path") or ""), artifact_root)
                detail = run_read_only_check(read_task, artifact_root)
                result = {**base, "status": "success", "finished_utc": utc(), "detail": detail, "mutation_performed": False}
            elif kind == "prebuilt_tool":
                from local_coder_tool_registry_v1 import run_tool

                tool_args = expand_artifact_root(dict(task.get("args") or {}), artifact_root)
                detail = run_tool(str(task.get("tool") or ""), tool_args)
                tool_result = detail.get("result") if isinstance(detail, dict) else None
                tool_failed = isinstance(tool_result, dict) and tool_result.get("pass") is False
                result = {**base, "status": "tool_fail" if tool_failed else "success", "finished_utc": utc(), "detail": detail, "mutation_performed": bool(not tool_failed and task_is_mutating(task))}
            else:
                prompt = str(task.get("prompt") or "")
                if not prompt.strip():
                    raise ValueError("draft_prompt_empty")
                if len(prompt) > MAX_PROMPT_CHARS:
                    raise ValueError(f"draft_prompt_exceeds_max:{len(prompt)}:{MAX_PROMPT_CHARS}")
                validate_draft_prompt(prompt)
                timeout_s = float(task.get("timeout_s", 180))
                if timeout_s <= 0.0 or timeout_s > MAX_TIMEOUT_S:
                    raise ValueError(f"draft_timeout_out_of_bounds:{timeout_s}:{MAX_TIMEOUT_S}")
                effective_prompt = CODER_CONTRACT + prompt
                prompt_hash = digest_text(prompt)
                effective_prompt_hash = digest_text(effective_prompt)
                draft_evidence.update({"prompt_sha256": prompt_hash, "effective_prompt_sha256": effective_prompt_hash})
                response = call_coder(effective_prompt, timeout_s=timeout_s)
                response_hash = digest_text(response)
                output_bytes = len(response.encode("utf-8"))
                draft_evidence.update({"response_sha256": response_hash, "output_bytes": output_bytes})
                if output_bytes > MAX_DRAFT_BYTES:
                    raise ValueError(f"draft_response_exceeds_max:{output_bytes}:{MAX_DRAFT_BYTES}")
                validate_draft_response(response, task)
                draft_name = str(task.get("draft_name") or f"{task_id}.txt")
                draft_path = resolve_inside(artifact_root / draft_name, (artifact_root,))
                if draft_path.exists():
                    raise FileExistsError(f"refuse_to_overwrite:{draft_path}")
                try:
                    write_text(draft_path, response, security)
                except Exception as write_exc:
                    result = {**base, "status": "error", "finished_utc": utc(), "prompt_sha256": prompt_hash, "effective_prompt_sha256": effective_prompt_hash, "response_sha256": response_hash, "output_path": str(draft_path).replace("\\", "/"), "output_bytes": output_bytes, "mutation_performed": False, "exception": f"{type(write_exc).__name__}:{write_exc}"}
                else:
                    result = {**base, "status": "success", "finished_utc": utc(), "prompt_sha256": prompt_hash, "effective_prompt_sha256": effective_prompt_hash, "response_sha256": response_hash, "output_path": str(draft_path).replace("\\", "/"), "output_bytes": output_bytes, "mutation_performed": True}
        except Exception as exc:  # fail this task, never retry or execute a later privileged action
            result = {**base, **draft_evidence, "status": "error", "finished_utc": utc(), "exception": f"{type(exc).__name__}:{exc}"}
        append_log(log_path, {"event": "task_end", **result}, security)
        results.append(result)
        previous_status = result["status"]
        state.update({"next_index": index + 1, "previous_status": previous_status, "results": results})
        persist_queue_state(state_path, state, security)
        if stop_after_tasks is not None and len(results) >= stop_after_tasks:
            state["status"] = "INTERRUPTED"
            persist_queue_state(state_path, state, security)
            update_current_task(status="INTERRUPTED", trace_id=trace_id, task_list_path=task_list_path, task_list_sha256=task_list_sha256, artifact_root=artifact_root, mode=mode, current_index=index + 1, total_tasks=len(tasks), next_action="resume_with_same_task_hash_and_mode", last_task=result, security=security)
            raise QueueInterrupted(f"queue_interrupted_after:{len(results)}")
    queue_failed = not all(item["status"] in {"success", "skipped_condition", "dry_run_would_execute"} for item in results)
    rollback_rows = rollback_mutations(results, security) if queue_failed else []
    if rollback_rows:
        for row in rollback_rows:
            append_log(log_path, {"event": "rollback", **row}, security)
    rollback_verified = not rollback_rows or all(row.get("status") == "rollback_verified" for row in rollback_rows)
    audit_chain_verified = verify_log_chain(log_path)
    rollback_receipt = {"schema_version": "local_coder_queue_rollback_v1", "required": queue_failed and any(item.get("mutation_performed") for item in results), "verified": rollback_verified, "rows": rollback_rows}
    write_text(artifact_root / "rollback_receipt.json", json.dumps(rollback_receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n", security)
    summary = {"schema_version": "local_coder_task_queue_v1", "status": "QUEUE_PASS" if not queue_failed else "QUEUE_FAIL", "created_utc": utc(), "task_list": str(task_list_path).replace("\\", "/"), "task_list_sha256": task_list_sha256, "artifact_root": str(artifact_root).replace("\\", "/"), "model": MODEL, "tasks": results, "retries": 0, "mode": mode, "operator_approved": bool(operator_approved), "trace_id": trace_id, "capability_manifest": str(CAPABILITY_MANIFEST_PATH).replace("\\", "/"), "capability_manifest_sha256": digest_file(CAPABILITY_MANIFEST_PATH), "shell_execution": False, "training": False, "lease_opened": False, "authorization_changed": False, "deployment_changed": False, "integration_allowed": False, "mutation_performed": any(item.get("mutation_performed") for item in results), "audit_chain_verified": audit_chain_verified, "rollback_verified": rollback_verified, "rollback_required": rollback_receipt["required"], "downstream_after_failure": any(item["status"] == "skipped_after_failure" for item in results)}
    state.update({"status": "COMPLETED", "next_index": len(tasks), "results": results})
    persist_queue_state(state_path, state, security)
    update_current_task(status="COMPLETED" if not queue_failed else "FAILED", trace_id=trace_id, task_list_path=task_list_path, task_list_sha256=task_list_sha256, artifact_root=artifact_root, mode=mode, current_index=len(tasks), total_tasks=len(tasks), next_action="review_summary_and_receipts" if queue_failed else "review_summary_or_start_next_bounded_task", last_task=results[-1] if results else None, security=security)
    write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", security)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run logged local-coder draft/read-only tasks")
    parser.add_argument("--task-list", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=sorted(QUEUE_MODES), default="dry_run")
    parser.add_argument("--operator-approve-mutations", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    summary = run_queue(args.task_list, args.artifact_dir, mode=args.mode, operator_approved=args.operator_approve_mutations, resume=args.resume)
    print(json.dumps({"ok": summary["status"] == "QUEUE_PASS", "status": summary["status"], "tasks": len(summary["tasks"]), "artifact_root": summary["artifact_root"]}, sort_keys=True))
    return 0 if summary["status"] == "QUEUE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
