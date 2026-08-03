"""Durable, fail-closed execution abort evidence."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_abort_report(
    path: Path,
    *,
    campaign_id: str,
    run_id: str,
    stage: str,
    exception_type: str,
    exception_message: str,
    traceback_text: str,
    trained_result: Any,
    commit_verdict: Any,
    quarantine_root: str | None,
    authority: dict[str, Any],
) -> dict[str, Any]:
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(f"refuse_to_overwrite:{destination}")
    report = {
        "schema_version": "execution_abort_report_v1",
        "recorded_utc": _utc(),
        "status": "ABORT_NO_PROMOTION",
        "campaign_id": str(campaign_id),
        "run_id": str(run_id),
        "stage": str(stage),
        "exception_type": str(exception_type),
        "exception_message": str(exception_message),
        "traceback": str(traceback_text),
        "trained_result": trained_result,
        "commit_verdict": commit_verdict,
        "quarantine_root": quarantine_root,
        "authority": dict(authority),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, ensure_ascii=False, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return report
