"""Live session log for auto_main autonomous — terminal output + full beat reports.

Operational logs are training corpus: Viv learns from what AIOS actually did,
not from narrative. Each event is append-only JSONL plus a live session JSON mirror.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from lib.paths import AUTO_ARTIFACTS

SESSION_LOG_PATH = AUTO_ARTIFACTS / "autonomous_session.json"
SESSION_LOG_JSONL = AUTO_ARTIFACTS / "autonomous_session.jsonl"
SESSION_ARCHIVE_PATH = AUTO_ARTIFACTS / "autonomous_session.previous.json"
SESSION_JSONL_ARCHIVE_PATH = AUTO_ARTIFACTS / "autonomous_session.previous.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


class AutonomousSessionLog:
    """Append-only session record mirrored to autonomous_session.json."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or SESSION_LOG_PATH
        self._data: dict[str, Any] = {}

    def start(self, *, config: dict[str, Any], startup: dict[str, Any]) -> None:
        if self.path.is_file():
            try:
                _atomic_write(SESSION_ARCHIVE_PATH, json.loads(self.path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        if SESSION_LOG_JSONL.is_file():
            try:
                SESSION_JSONL_ARCHIVE_PATH.write_text(
                    SESSION_LOG_JSONL.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                SESSION_LOG_JSONL.unlink()
            except OSError:
                pass
        started = _utc_now()
        self._data = {
            "pillar": "auto",
            "session_id": f"{started.replace(':', '').replace('-', '')[:15]}-{uuid4().hex[:8]}",
            "status": "running",
            "started_at": started,
            "stopped_at": None,
            "beats_completed": 0,
            "config": config,
            "startup": startup,
            "log_path_jsonl": str(SESSION_LOG_JSONL),
            "log": [],
        }
        self._flush()
        self._append_jsonl({"kind": "session_start", "session_id": self._data["session_id"], "config": config, "startup": startup})

    def terminal(self, text: str, *, stream: str = "stdout") -> None:
        self._append(
            {
                "at": _utc_now(),
                "kind": "terminal",
                "stream": stream,
                "text": text.rstrip("\n"),
            }
        )

    def beat(self, *, beat_no: int, terminal_line: str, report: dict[str, Any]) -> None:
        self._data["beats_completed"] = beat_no
        self._append(
            {
                "at": _utc_now(),
                "kind": "beat",
                "beat": beat_no,
                "terminal_line": terminal_line,
                "report": report,
            }
        )

    def error(self, text: str) -> None:
        self._append({"at": _utc_now(), "kind": "error", "text": text})

    def shutdown(self, *, reason: str, beats: int, extra: dict[str, Any] | None = None) -> None:
        self._data["status"] = "stopped"
        self._data["stopped_at"] = _utc_now()
        self._data["beats_completed"] = beats
        row: dict[str, Any] = {
            "at": _utc_now(),
            "kind": "shutdown",
            "reason": reason,
            "beats": beats,
        }
        if extra:
            row.update(extra)
        self._append(row, flush_session=False)
        self._flush()

    def record_startup(self, **fields: Any) -> None:
        if not self._data:
            return
        self._data.setdefault("startup", {}).update(fields)
        self._flush()

    def _append(self, row: dict[str, Any], *, flush_session: bool = True) -> None:
        if not self._data:
            return
        self._data.setdefault("log", []).append(row)
        out = {"session_id": self._data.get("session_id"), **row}
        self._append_jsonl(out)
        if flush_session:
            self._flush()

    def _append_jsonl(self, row: dict[str, Any]) -> None:
        SESSION_LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with SESSION_LOG_JSONL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")

    def _flush(self) -> None:
        if self._data:
            _atomic_write(self.path, self._data)


def format_beat_terminal_line(beat: dict[str, Any]) -> str:
    mode = beat.get("mode", "?")
    line = beat.get("narrator_line") or beat.get("line", "")
    rt = beat.get("runtime_tick")
    rt_s = ""
    if isinstance(rt, dict) and rt.get("skipped"):
        rt_s = " rt=skip"
    elif isinstance(rt, dict) and "exit_code" in rt:
        rt_s = f" rt={rt.get('exit_code')}"
    plant_v = (beat.get("plant") or {}).get("verdict", "-")
    msn = beat.get("master_s_n") or (beat.get("sample") or {}).get("s_n", 0)
    try:
        msn_f = float(msn)
    except (TypeError, ValueError):
        msn_f = 0.0
    voice = beat.get("voice_line") or ""
    if isinstance(voice, str) and voice.strip():
        v_s = f" | voice={voice.strip()[:120]}"
    else:
        v_s = ""
    return f"[{mode}] Master_S_n={msn_f:.4f} | {line} | plant={plant_v}{rt_s}{v_s}"
