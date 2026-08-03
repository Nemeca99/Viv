"""Plan-only CPU cleanup decisions for the local file-index boundary."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md#data-cleanup-operations"
INDEX_SOURCE = "foundation/scripts/file_index_system.py"
PROTECTED_NEEDLES = ("/windows/", "/program files/", "/programdata/", "/system volume information/", "/$recycle.bin/")


def _protected(path: str) -> bool:
    clean = str(path).replace("\\", "/").casefold()
    return any(needle in clean for needle in PROTECTED_NEEDLES)


def build_plan(candidates: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for raw in candidates:
        path = str(raw.get("path") or "").strip()
        duplicate = bool(raw.get("duplicate") or raw.get("duplicate_group"))
        canonical = bool(raw.get("canonical", False))
        readonly = bool(raw.get("readonly", False))
        protected = bool(raw.get("system_path")) or _protected(path)
        if not path:
            decision, reason = "DENY", "missing_path"
        elif protected:
            decision, reason = "DENY", "protected_system_path"
        elif readonly:
            decision, reason = "REVIEW", "readonly_requires_operator"
        elif duplicate and not canonical:
            decision, reason = "REVIEW", "verified_duplicate_candidate"
        else:
            decision, reason = "NO_ACTION", "not_eligible"
        rows.append({"path": path, "decision": decision, "reason": reason, "duplicate": duplicate, "canonical": canonical, "readonly": readonly, "protected": protected, "move_performed": False, "delete_performed": False})
    return {"ok": True, "state": "VERIFIED_PLAN_ONLY", "rows": rows, "review_count": sum(row["decision"] == "REVIEW" for row in rows), "deny_count": sum(row["decision"] == "DENY" for row in rows), "plan_only": True, "backup_required_before_effect": True, "moves_performed": False, "deletes_performed": False, "execution_authority": "not_granted", "manual_source": MANUAL_SOURCE, "index_source": INDEX_SOURCE}
