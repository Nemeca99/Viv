"""Read-only CPU policy boundary for Viv's mutation sandbox.

This module evaluates requests; it never writes, executes, promotes, or
deletes. Existing gated adapters remain the only effect authority.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from lib.aios_sandbox import SANDBOX_ROOT

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_SANDBOX_FILES = 100
ALLOWED_EXTENSIONS = frozenset({".py", ".json", ".yaml", ".yml", ".txt", ".md"})
ALLOWED_OPERATIONS = frozenset({"read_file", "list_files", "review_code", "verify_syntax", "write_file"})
FORBIDDEN_IMPORTS = frozenset({"subprocess", "os", "socket", "requests", "ctypes", "sys"})
FORBIDDEN_CALLS = frozenset({"eval", "exec", "compile", "__import__", "breakpoint"})
FORBIDDEN_PATTERNS = (
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"\bos\.popen\s*\("),
    re.compile(r"\bshutil\.rmtree\s*\("),
    re.compile(r"\brequests\.(get|post|put|delete)\s*\("),
)


def _path(path: Any) -> tuple[Path | None, str | None]:
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        return None, "path_invalid"
    raw = path.replace("\\", "/")
    if raw.startswith(("/", "~")) or ":" in raw or any(part == ".." for part in raw.split("/")):
        return None, "path_escape_denied"
    candidate = (SANDBOX_ROOT / raw).resolve()
    try:
        candidate.relative_to(SANDBOX_ROOT.resolve())
    except ValueError:
        return None, "path_outside_sandbox"
    if candidate.suffix and candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        return None, "extension_denied"
    return candidate, None


def validate_path(path: Any, *, for_write: bool = False) -> dict[str, Any]:
    candidate, reason = _path(path)
    if candidate is None:
        return {"ok": False, "state": "DENIED", "reason": reason, "writes": False}
    if candidate.exists() and candidate.is_file() and candidate.stat().st_size > MAX_FILE_BYTES:
        return {"ok": False, "state": "DENIED", "reason": "file_size_limit", "writes": False}
    if for_write and not candidate.parent.is_dir():
        return {"ok": False, "state": "DENIED", "reason": "parent_missing", "writes": False}
    return {"ok": True, "state": "VERIFIED", "path": str(candidate).replace("\\", "/"), "for_write": for_write, "writes": False}


def scan_code(source: Any) -> dict[str, Any]:
    if not isinstance(source, str):
        return {"ok": False, "state": "DENIED", "reason": "source_invalid", "violations": [], "writes": False}
    violations: list[str] = []
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(source):
            violations.append(f"forbidden_pattern:{pattern.pattern}")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"ok": False, "state": "DENIED", "reason": "syntax_invalid", "violations": [str(exc)], "writes": False}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            violations.extend(f"forbidden_import:{alias.name}" for alias in node.names if alias.name.split(".")[0] in FORBIDDEN_IMPORTS)
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in FORBIDDEN_IMPORTS:
            violations.append(f"forbidden_import:{node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            violations.append(f"forbidden_call:{node.func.id}")
    return {"ok": not violations, "state": "VERIFIED" if not violations else "DENIED", "violations": sorted(set(violations)), "writes": False}


def evaluate_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a sandbox request without granting effect authority."""
    operation = payload.get("operation")
    if operation not in ALLOWED_OPERATIONS:
        return {"ok": False, "state": "DENIED", "reason": "operation_not_allowlisted", "writes": False}
    path_result = validate_path(payload.get("path"), for_write=operation == "write_file")
    if not path_result.get("ok"):
        return {**path_result, "operation": operation}
    code_result = scan_code(payload["source"]) if "source" in payload else {"ok": True, "state": "NOT_APPLICABLE", "violations": [], "writes": False}
    if not code_result.get("ok"):
        return {"ok": False, "state": "DENIED", "operation": operation, "path": path_result.get("path"), "code": code_result, "writes": False}
    return {
        "ok": True,
        "state": "VERIFIED_PLAN_ONLY",
        "operation": operation,
        "path": path_result["path"],
        "code": code_result,
        "backup_required_before_effect": operation == "write_file",
        "effect_authorized": False,
        "writes": False,
        "executes": False,
        "promotes": False,
    }
