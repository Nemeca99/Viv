"""Bounded read-only snapshot of local state used by CPU choice policy."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from lib.master_rid import load_master_rid
from lib.paths import AUTO_ARTIFACTS

SNAPSHOT_VERSION = "cpu_state_snapshot_v1"
QUEUE_PATH = AUTO_ARTIFACTS / "agentic" / "task_queue.json"
DREAM_STATE_PATH = AUTO_ARTIFACTS / "organism" / "dream_state.json"


def build_snapshot(*, s_n: float, queued_work: int, memory_due: bool = False, restore_due: bool = False, system_awake: bool = True, sources: Mapping[str, str] | None = None) -> dict[str, Any]:
    return {
        "version": SNAPSHOT_VERSION,
        "s_n": max(0.0, min(float(s_n), 1.0)),
        "queued_work": max(0, int(queued_work)),
        "memory_due": bool(memory_due),
        "restore_due": bool(restore_due),
        "system_awake": bool(system_awake),
        "sources": dict(sources or {}),
        "read_only": True,
        "writes_performed": False,
        "llm_authority": False,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def capture_live() -> dict[str, Any]:
    """Read current local state without changing queue, RID, or dream artifacts."""
    try:
        s_n = float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        s_n = 0.5
    queue = _read_json(QUEUE_PATH)
    tasks = queue.get("tasks") if isinstance(queue.get("tasks"), list) else []
    queued = sum(1 for task in tasks if isinstance(task, dict) and task.get("status", "ready") in {"ready", "running"})
    dream = _read_json(DREAM_STATE_PATH)
    return build_snapshot(
        s_n=s_n,
        queued_work=queued,
        memory_due=bool(dream.get("memory_due", False)),
        restore_due=bool(dream.get("restore_due", False)),
        sources={"rid": "lib.master_rid.load_master_rid", "queue": str(QUEUE_PATH).replace("\\", "/"), "dream": str(DREAM_STATE_PATH).replace("\\", "/")},
    )
