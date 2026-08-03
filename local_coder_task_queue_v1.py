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
    write_text(path, prior + json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n", security)


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


def run_queue(task_list_path: Path, artifact_root: Path, *, secure_writes: bool = True) -> dict[str, Any]:
    task_list_path = resolve_inside(Path(task_list_path), ALLOWED_READ_ROOTS + (artifact_root,))
    artifact_root = Path(artifact_root).resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    security = _security_context() if secure_writes else None
    log_path = artifact_root / "queue_log.jsonl"
    summary_path = artifact_root / "queue_summary.json"
    if log_path.exists():
        raise FileExistsError(f"refuse_to_append_existing_queue_log:{log_path}")
    if summary_path.exists():
        raise FileExistsError(f"refuse_to_overwrite:{summary_path}")
    tasks = json.loads(task_list_path.read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise ValueError("task_list_must_be_array")
    if len(tasks) > MAX_TASKS:
        raise ValueError(f"task_count_exceeds_max:{len(tasks)}:{MAX_TASKS}")
    previous_status: str | None = None
    results: list[dict[str, Any]] = []
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
        kind = str(task.get("kind") or "")
        if kind in FORBIDDEN_TASK_KINDS or kind not in {"draft_code", "read_only_check", "prebuilt_tool"}:
            raise ValueError(f"task_kind_denied:{task_id}:{kind}")
        condition = task.get("if_previous_status")
        start = utc()
        base = {"task_id": task_id, "index": index, "kind": kind, "model": MODEL if kind == "draft_code" else None, "tool": task.get("tool") if kind == "prebuilt_tool" else None, "started_utc": start}
        append_log(log_path, {"event": "task_start", **base, "previous_status": previous_status, "if_previous_status": condition}, security)
        if previous_status in {"error", "tool_fail"} and condition is None:
            result = {**base, "status": "skipped_after_failure", "finished_utc": utc(), "previous_status": previous_status, "skip_reason": "explicit_if_previous_status_required_after_failure"}
            append_log(log_path, {"event": "task_end", **result}, security)
            results.append(result)
            previous_status = result["status"]
            continue
        if condition is not None and condition != previous_status:
            result = {**base, "status": "skipped_condition", "finished_utc": utc(), "previous_status": previous_status}
            append_log(log_path, {"event": "task_end", **result}, security)
            results.append(result)
            previous_status = result["status"]
            continue
        draft_evidence: dict[str, Any] = {}
        try:
            if kind == "read_only_check":
                detail = run_read_only_check(task, artifact_root)
                result = {**base, "status": "success", "finished_utc": utc(), "detail": detail}
            elif kind == "prebuilt_tool":
                from local_coder_tool_registry_v1 import run_tool

                tool_args = expand_artifact_root(dict(task.get("args") or {}), artifact_root)
                detail = run_tool(str(task.get("tool") or ""), tool_args)
                tool_result = detail.get("result") if isinstance(detail, dict) else None
                tool_failed = isinstance(tool_result, dict) and tool_result.get("pass") is False
                result = {**base, "status": "tool_fail" if tool_failed else "success", "finished_utc": utc(), "detail": detail}
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
                    result = {**base, "status": "error", "finished_utc": utc(), "prompt_sha256": prompt_hash, "effective_prompt_sha256": effective_prompt_hash, "response_sha256": response_hash, "output_path": str(draft_path).replace("\\", "/"), "output_bytes": output_bytes, "exception": f"{type(write_exc).__name__}:{write_exc}"}
                else:
                    result = {**base, "status": "success", "finished_utc": utc(), "prompt_sha256": prompt_hash, "effective_prompt_sha256": effective_prompt_hash, "response_sha256": response_hash, "output_path": str(draft_path).replace("\\", "/"), "output_bytes": output_bytes}
        except Exception as exc:  # fail this task, never retry or execute a later privileged action
            result = {**base, **draft_evidence, "status": "error", "finished_utc": utc(), "exception": f"{type(exc).__name__}:{exc}"}
        append_log(log_path, {"event": "task_end", **result}, security)
        results.append(result)
        previous_status = result["status"]
    summary = {"schema_version": "local_coder_task_queue_v1", "status": "QUEUE_PASS" if all(item["status"] in {"success", "skipped_condition"} for item in results) else "QUEUE_FAIL", "created_utc": utc(), "task_list": str(task_list_path).replace("\\", "/"), "task_list_sha256": digest_file(task_list_path), "artifact_root": str(artifact_root).replace("\\", "/"), "model": MODEL, "tasks": results, "retries": 0, "shell_execution": False, "training": False, "lease_opened": False, "authorization_changed": False, "deployment_changed": False, "integration_allowed": False, "downstream_after_failure": any(item["status"] == "skipped_after_failure" for item in results)}
    write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", security)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run logged local-coder draft/read-only tasks")
    parser.add_argument("--task-list", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = run_queue(args.task_list, args.artifact_dir)
    print(json.dumps({"ok": summary["status"] == "QUEUE_PASS", "status": summary["status"], "tasks": len(summary["tasks"]), "artifact_root": summary["artifact_root"]}, sort_keys=True))
    return 0 if summary["status"] == "QUEUE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
