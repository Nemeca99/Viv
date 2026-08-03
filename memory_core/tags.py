"""Master tag file — tags are never deleted, only added or updated."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from memory_core.paths import MASTER_TAGS_PATH


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default() -> dict[str, Any]:
    return {"version": 1, "tags": {}, "updated_at": _utc()}


def load_tags() -> dict[str, Any]:
    if not MASTER_TAGS_PATH.is_file():
        return _default()
    try:
        return json.loads(MASTER_TAGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _default()


def save_tags(data: dict[str, Any]) -> None:
    data["updated_at"] = _utc()
    MASTER_TAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = MASTER_TAGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(MASTER_TAGS_PATH)


def define_tag(name: str, description: str = "") -> dict[str, Any]:
    data = load_tags()
    tags = data.setdefault("tags", {})
    key = name.strip().lower()
    if not key:
        raise ValueError("empty tag name")
    row = tags.get(key, {})
    row["name"] = key
    row["description"] = description or row.get("description", "")
    row["updated_at"] = _utc()
    if "created_at" not in row:
        row["created_at"] = row["updated_at"]
    tags[key] = row
    save_tags(data)
    return row


def list_tags() -> list[dict[str, Any]]:
    data = load_tags()
    return sorted(data.get("tags", {}).values(), key=lambda r: r.get("name", ""))
