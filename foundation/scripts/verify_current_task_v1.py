#!/usr/bin/env python3
"""Read-only verification for Viv's cross-thread current-task contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CURRENT_TASK = Path(__file__).resolve().parents[1] / "artifacts" / "auto" / "agentic" / "CURRENT_TASK.json"
ALLOWED_STATUS = {"IN_PROGRESS", "INTERRUPTED", "COMPLETED", "FAILED"}


def verify(path: Path = CURRENT_TASK) -> dict[str, Any]:
    findings: list[str] = []
    if not path.is_file():
        return {"schema_version": "viv_current_task_verification_v1", "verified": False, "findings": [f"missing:{path}"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"schema_version": "viv_current_task_verification_v1", "verified": False, "findings": [f"read_or_json_error:{type(exc).__name__}:{exc}"]}
    if data.get("schema_version") != "viv_current_task_v1":
        findings.append("schema_version_invalid")
    if data.get("status") not in ALLOWED_STATUS:
        findings.append("status_invalid")
    if not isinstance(data.get("trace_id"), str) or not data["trace_id"]:
        findings.append("trace_id_missing")
    index = data.get("current_index")
    total = data.get("total_tasks")
    if not isinstance(index, int) or not isinstance(total, int) or index < 0 or total < 0 or index > total:
        findings.append("task_progress_invalid")
    authority = data.get("authority") or {}
    for key in ("training", "lease_opened", "authorization_changed", "deployment_changed"):
        if authority.get(key) is not False:
            findings.append(f"authority_not_closed:{key}")
    if not isinstance(data.get("next_action"), str) or not data["next_action"].strip():
        findings.append("next_action_missing")
    return {"schema_version": "viv_current_task_verification_v1", "verified": not findings, "path": str(path).replace("\\", "/"), "status": data.get("status"), "trace_id": data.get("trace_id"), "current_index": index, "total_tasks": total, "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Viv CURRENT_TASK.json without writing")
    parser.add_argument("--path", type=Path, default=CURRENT_TASK)
    args = parser.parse_args()
    result = verify(args.path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
