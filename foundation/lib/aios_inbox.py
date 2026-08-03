"""Operator inbox + task board — asks become full Missions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.agentic_runtime import load_queue
from lib.paths import AUTO_ARTIFACTS
from lib.aios_sandbox import SANDBOX_ROOT

ORGANISM_ROOT = AUTO_ARTIFACTS / "organism"
INBOX_PATH = ORGANISM_ROOT / "inbox.jsonl"
OUTBOX_PATH = ORGANISM_ROOT / "outbox.jsonl"
TASK_BOARD_JSON = ORGANISM_ROOT / "task_board.json"
TASK_BOARD_MD = ORGANISM_ROOT / "task_board.md"
SANDBOX = SANDBOX_ROOT


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def submit(
    text: str,
    *,
    action: str | None = None,
    priority: int = 25,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operator ask → inbox + full Mission (multi-step). Safe while organism runs."""
    row: dict[str, Any] = {
        "id": f"in-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": _utc(),
        "text": (text or "").strip(),
        "action": action,
        "priority": int(priority),
        "payload": payload or {},
        "status": "queued",
    }
    _append_jsonl(INBOX_PATH, row)
    try:
        from lib.aios_missions import create_mission

        mission = create_mission(row["text"])
        row["mission_id"] = mission.mission_id
        row["steps"] = [s.name for s in mission.steps]
        # Rewrite last inbox line with mission_id so drain won't duplicate
        if INBOX_PATH.is_file():
            lines = INBOX_PATH.read_text(encoding="utf-8").splitlines()
            if lines:
                try:
                    last = json.loads(lines[-1])
                    if last.get("id") == row["id"]:
                        last["mission_id"] = row["mission_id"]
                        last["steps"] = row["steps"]
                        lines[-1] = json.dumps(last, ensure_ascii=False)
                        INBOX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
                except json.JSONDecodeError:
                    pass
        _append_jsonl(
            OUTBOX_PATH,
            {
                "event": "mission_queued",
                "timestamp": _utc(),
                "ask": row["text"],
                "mission_id": mission.mission_id,
                "steps": row["steps"],
            },
        )
    except Exception as exc:  # noqa: BLE001
        row["mission_error"] = str(exc)
    return row


def drain_inbox(*, limit: int = 20) -> dict[str, Any]:
    """Mark inbox accepted. Missions are created at submit-time."""
    if not INBOX_PATH.is_file():
        return {"drained": 0, "enqueued": 0, "items": [], "missions": []}

    lines = INBOX_PATH.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    drained: list[dict[str, Any]] = []
    n = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        if item.get("status") not in (None, "queued"):
            kept.append(json.dumps(item, ensure_ascii=False))
            continue
        if n >= limit:
            kept.append(json.dumps(item, ensure_ascii=False))
            continue
        item["status"] = "accepted"
        item["accepted_at"] = _utc()
        if not item.get("mission_id"):
            try:
                from lib.aios_missions import create_mission

                m = create_mission(str(item.get("text") or ""))
                item["mission_id"] = m.mission_id
                item["steps"] = [s.name for s in m.steps]
            except Exception as exc:  # noqa: BLE001
                item["mission_error"] = str(exc)
        drained.append(item)
        _append_jsonl(OUTBOX_PATH, {"event": "inbox_accepted", **item})
        n += 1

    INBOX_PATH.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return {
        "drained": len(drained),
        "enqueued": 0,
        "items": drained,
        "missions": [d.get("mission_id") for d in drained if d.get("mission_id")],
        "task_ids": [],
    }


def publish_task_board(*, beat: dict[str, Any] | None = None) -> dict[str, Any]:
    """Human-visible missions + micro-queue snapshot."""
    tasks = load_queue()
    by_status: dict[str, list[dict[str, Any]]] = {}
    for t in tasks:
        by_status.setdefault(t.status, []).append(
            {
                "task_id": t.task_id,
                "kind": t.kind,
                "title": t.title,
                "priority": t.priority,
                "status": t.status,
                "updated_at": t.updated_at,
            }
        )

    missions_info: dict[str, Any] = {}
    try:
        from lib.aios_missions import missions_board, publish_activity_md

        missions_info = missions_board()
        publish_activity_md()
    except Exception as exc:  # noqa: BLE001
        missions_info = {"error": str(exc)}

    board = {
        "updated_at": _utc(),
        "counts": {k: len(v) for k, v in by_status.items()},
        "ready": (by_status.get("ready") or [])[:20],
        "missions": missions_info,
        "inbox_path": str(INBOX_PATH).replace("\\", "/"),
        "activity_md": "L:/Continue/Viv/foundation/artifacts/auto/organism/ACTIVITY.md",
        "beat": {
            "master_s_n": (beat or {}).get("master_s_n"),
            "missions_run": (beat or {}).get("missions_run"),
        }
        if beat
        else None,
    }
    ORGANISM_ROOT.mkdir(parents=True, exist_ok=True)
    TASK_BOARD_JSON.write_text(json.dumps(board, indent=2, default=str), encoding="utf-8")

    lines = [f"# Viv task board — {board['updated_at']}", "", "## Missions (full work)"]
    for m in missions_info.get("ready") or []:
        lines.append(f"- READY `{m['mission_id']}` — {m['ask']}")
        for s in m.get("steps") or []:
            lines.append(f"  - [{s.get('status')}] {s.get('name')}")
    for m in (missions_info.get("done_tail") or [])[-8:]:
        lines.append(f"- DONE `{m['mission_id']}` — {m['ask']}")
        if m.get("spoken"):
            lines.append(f"  - said: {str(m['spoken'])[:180]}")
    if not (missions_info.get("ready") or missions_info.get("done_tail")):
        lines.append('- (none — `aios_main.py ask "..."`)')
    lines.extend(
        [
            "",
            "## Surfaces",
            "- Ask: `aios_main.py ask \"...\"`",
            "- Activity: `L:/Continue/Viv/foundation/artifacts/auto/organism/ACTIVITY.md`",
            "- Missions: `L:/Continue/Viv/foundation/artifacts/auto/organism/missions.json`",
            "- Sandbox (Law 7 home): `L:/Continue/Viv/sandbox/`",
            "-   code/ dream/ journal/ work/ operator/ sessions/",
        ]
    )
    TASK_BOARD_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return board


def report_outbox(event: str, **fields: Any) -> None:
    _append_jsonl(OUTBOX_PATH, {"event": event, "timestamp": _utc(), **fields})
