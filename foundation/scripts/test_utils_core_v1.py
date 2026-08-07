"""Focused tests for the effect-closed ``utils_core`` CPU boundary."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.utils_core import (  # noqa: E402
    classify_path,
    make_message_envelope,
    module_status,
    plan_bridge_call,
    plan_file_operation,
    plan_retry,
    timestamp_age,
    validate_input,
    validate_message_envelope,
)


def main() -> int:
    valid = validate_input({"name": "Viv", "parts": [1, 2]}, kind="json")
    invalid = validate_input({"value": float("nan")}, kind="json")
    assert valid["ok"] is True and valid["digest"], valid
    assert invalid["ok"] is False, invalid

    text = validate_input("hello\nworld", kind="text")
    assert text["ok"] is True and text["digest"], text

    retry = plan_retry(max_retries=3, base_delay_seconds=2, multiplier=2, max_delay_seconds=60)
    assert retry["ok"] and retry["delays_seconds"] == [2.0, 4.0, 8.0], retry
    assert retry["sleep_performed"] is False and retry["execution_performed"] is False, retry

    allowed = classify_path(
        "L:/Continue/Viv/foundation/lib/utils_core.py",
        allowed_roots=("L:/Continue",),
    )
    denied = classify_path(
        "L:/Continue/Viv/../outside.py",
        allowed_roots=("L:/Continue",),
    )
    effectful = plan_file_operation("L:/Continue/Viv/file.txt", operation="write", allowed_roots=("L:/Continue",))
    assert allowed["ok"] is True and allowed["filesystem_resolved"] is False, allowed
    assert denied["ok"] is False and "path_traversal_segment" in denied["errors"], denied
    assert effectful["ok"] is False and effectful["execution_approved"] is False, effectful

    fresh = timestamp_age("2026-08-04T12:00:00Z", "2026-08-04T12:00:02Z", stale_after_seconds=3)
    stale = timestamp_age("2026-08-04T12:00:00Z", "2026-08-04T12:00:04Z", stale_after_seconds=3)
    assert fresh["ok"] and fresh["stale"] is False, fresh
    assert stale["ok"] and stale["stale"] is True, stale

    envelope = make_message_envelope("data_core", "rag_core", "request", {"query": "hello"}, priority=2)
    checked = validate_message_envelope(envelope)
    tampered = {**envelope, "data": {"query": "changed"}}
    assert checked["ok"] is True, checked
    assert validate_message_envelope(tampered)["ok"] is False, tampered

    bridge = plan_bridge_call("powershell", "Get-AIOSStatus")
    assert bridge["ok"] and bridge["execution_approved"] is False, bridge
    status = module_status()
    assert status["ok"] and status["filesystem_write_performed"] is False, status

    source = (FOUNDATION / "lib" / "utils_core.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {"subprocess", "socket", "requests", "torch"}
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    )
    assert not imported.intersection(forbidden_imports), imported
    forbidden_calls = {"open", "sleep", "system", "run", "Popen", "write_text", "mkdir", "unlink"}
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls.intersection(forbidden_calls), calls

    print(
        json.dumps(
            {
                "ok": True,
                "retry_delays": retry["delays_seconds"],
                "fresh_age_seconds": fresh["age_seconds"],
                "stale_age_seconds": stale["age_seconds"],
                "message_id": envelope["message_id"],
                "bridge_execution_approved": bridge["execution_approved"],
                "filesystem_write_performed": False,
                "execution_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
