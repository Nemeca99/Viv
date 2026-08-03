"""SemanticMemory — plain-text CARMA API (Law 2: only through this interface)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_core.gate import current_s_n, gated_write
from memory_core.paths import (
    CARMA_ROOT,
    CURRENT_TXT,
    HEARTBEAT_PATH,
    INDEX_PATH,
    MASTER_TAGS_PATH,
    PROVENANCE_DIRS,
    as_gate_path,
)
from memory_core.retrieve import carma_file_count, index_summary, retrieve as _retrieve
from memory_core.split import needs_split, split_file
from memory_core.tags import define_tag, list_tags, load_tags, save_tags


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_layout() -> None:
    CARMA_ROOT.mkdir(parents=True, exist_ok=True)
    for d in PROVENANCE_DIRS.values():
        d.mkdir(parents=True, exist_ok=True)
    if not MASTER_TAGS_PATH.is_file():
        save_tags({"version": 1, "tags": {}, "updated_at": _utc()})
    if not INDEX_PATH.is_file():
        _write_index({"version": 1, "entries": [], "files": [], "updated_at": _utc()})
    if not CURRENT_TXT.is_file():
        CURRENT_TXT.write_text("", encoding="utf-8")


def _write_index(data: dict[str, Any]) -> None:
    data["updated_at"] = _utc()
    tmp = INDEX_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(INDEX_PATH)


def _load_index() -> dict[str, Any]:
    ensure_layout()
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "entries": [], "files": []}


def _append_heartbeat(event: dict[str, Any]) -> None:
    row = dict(event)
    row.setdefault("timestamp", _utc())
    with HEARTBEAT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _format_line(text: str, provenance: str, tags: list[str] | None) -> str:
    prov = provenance.strip().lower() or "live"
    tag_part = "".join(f"[{t.strip().lower()}]" for t in (tags or []) if t.strip())
    return f"[{prov}]{tag_part}[{_utc()}] {text.rstrip()}\n"


class SemanticMemory:
    """Plain-text memory — retrieve, compute, verify; no hallucinated store."""

    def remember(
        self,
        text: str,
        *,
        provenance: str = "live",
        tags: list[str] | None = None,
        s_n: float | None = None,
    ) -> dict[str, Any]:
        return remember(text, provenance=provenance, tags=tags, s_n=s_n)

    def retrieve(self, query: str, *, top: int = 5, tags: list[str] | None = None) -> list[dict[str, Any]]:
        return retrieve(query, top=top, tags=tags)

    def status(self) -> dict[str, Any]:
        return status()


def remember(
    text: str,
    *,
    provenance: str = "live",
    tags: list[str] | None = None,
    s_n: float | None = None,
    target_path: Path | None = None,
) -> dict[str, Any]:
    ensure_layout()
    sn = float(s_n if s_n is not None else current_s_n())
    if sn < 0.15:
        return {"ok": False, "reason": "collapse", "s_n": sn}

    prov = provenance.strip().lower() or "live"
    if prov not in PROVENANCE_DIRS:
        prov = "live"
    path = target_path or (PROVENANCE_DIRS[prov] / "current.txt")
    line = _format_line(text, prov, tags)

    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    new_content = existing + line
    gate_path = as_gate_path(path)
    ok, reason, verdict = gated_write(gate_path, new_content, sn)
    if not ok:
        return {"ok": False, "reason": reason, "verdict": verdict}

    entry_id = f"m-{uuid.uuid4().hex[:10]}"
    idx = _load_index()
    idx.setdefault("entries", []).append(
        {
            "id": entry_id,
            "path": gate_path,
            "provenance": prov,
            "tags": [t.strip().lower() for t in (tags or []) if t.strip()],
            "at": _utc(),
            "preview": text[:120],
        }
    )
    files = set(idx.get("files") or [])
    files.add(gate_path)
    idx["files"] = sorted(files)
    _write_index(idx)

    _append_heartbeat({"event": "remember", "id": entry_id, "path": gate_path, "provenance": prov, "s_n": sn})

    split_result = None
    if needs_split(path):
        split_result = split_file(path, sn)
        if split_result and "error" not in split_result:
            idx = _load_index()
            for shard in (split_result.get("left"), split_result.get("right")):
                if shard:
                    files = set(idx.get("files") or [])
                    files.add(shard)
                    idx["files"] = sorted(files)
                    idx.setdefault("entries", []).append(
                        {
                            "id": f"m-{uuid.uuid4().hex[:10]}",
                            "path": shard,
                            "provenance": prov,
                            "tags": ["split_shard"],
                            "at": _utc(),
                            "preview": "split_shard",
                        }
                    )
            _write_index(idx)
            _append_heartbeat({"event": "split", "result": split_result, "s_n": sn})

    return {
        "ok": True,
        "id": entry_id,
        "path": gate_path,
        "provenance": prov,
        "split": split_result,
        "s_n": sn,
    }


def append_live_note(text: str, *, s_n: float | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    """Compact autonomous beat note — past anchored to heartbeat."""
    return remember(text, provenance="live", tags=tags or ["autonomous"], s_n=s_n)


def retrieve(query: str, *, top: int = 5, tags: list[str] | None = None) -> list[dict[str, Any]]:
    ensure_layout()
    return _retrieve(query, top=top, tags=tags)


def status() -> dict[str, Any]:
    ensure_layout()
    hb_lines = 0
    if HEARTBEAT_PATH.is_file():
        hb_lines = sum(1 for _ in HEARTBEAT_PATH.open(encoding="utf-8"))
    current_bytes = CURRENT_TXT.stat().st_size if CURRENT_TXT.is_file() else 0
    return {
        "owner": "viv",
        "carma_root": as_gate_path(CARMA_ROOT),
        "index": index_summary(),
        "txt_files": carma_file_count(),
        "heartbeat_lines": hb_lines,
        "current_bytes": current_bytes,
        "tags_defined": len(load_tags().get("tags") or {}),
        "master_tags_path": as_gate_path(MASTER_TAGS_PATH),
    }
