"""Effect-closed CPU planning for the governed AIOS ``backup_core``.

``foundation.lib.backup_core`` is the existing security-governed executor: it
hashes real files, writes immutable objects, stages restores, and requires the
Rust/Architect gates for effects.  This module is intentionally separate. It
lets the CPU validate snapshot/restore intent and manifest evidence before an
executor is considered, without reading the filesystem or requesting a
security decision.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any


MODULE_ID = "backup_core"
VERSION = "cpu-plan-v1"
MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.10 backup_core"
SOURCE_ROOT = "F:/AIOS_Clean/backup_core"
MAX_ITEMS = 100_000
MAX_RETENTION = 10_000
DEFAULT_ALLOWED_ROOTS = ("L:/Continue/Viv",)
_HASH = re.compile(r"^[0-9a-fA-F]{64}$")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _flags() -> dict[str, bool]:
    return {
        "filesystem_scan_performed": False,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "security_authorization_requested": False,
        "live_restore_performed": False,
        "deletion_performed": False,
        "llm_authority": False,
    }


def _result(ok: bool, **fields: Any) -> dict[str, Any]:
    result = {"ok": bool(ok), **fields}
    result.update(_flags())
    return result


def _path(path: Any, *, allowed_roots: Iterable[str] = DEFAULT_ALLOWED_ROOTS) -> tuple[str, list[str]]:
    text = str(path or "").strip().replace("\\", "/")
    errors: list[str] = []
    if not text:
        errors.append("path_is_empty")
    if any(ord(char) < 32 for char in text):
        errors.append("path_contains_control_character")
    parts = [part for part in text.split("/") if part]
    if ".." in parts:
        errors.append("path_traversal_segment")
    folded = text.casefold().rstrip("/")
    roots = [str(root).replace("\\", "/").casefold().rstrip("/") for root in allowed_roots]
    if roots and not any(folded == root or folded.startswith(root + "/") for root in roots):
        errors.append("path_outside_declared_backup_root")
    return text, errors


def _snapshot_id(value: Any) -> str:
    return str(value or "").strip().casefold()


def _valid_snapshot_id(value: Any) -> bool:
    return bool(_HASH.fullmatch(_snapshot_id(value)))


def _item_rows(items: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for raw in list(items)[:MAX_ITEMS]:
        if not isinstance(raw, Mapping):
            errors.append("item_not_mapping")
            continue
        path, path_errors = _path(raw.get("path"))
        digest = _snapshot_id(raw.get("sha256"))
        try:
            size = int(raw.get("bytes", 0))
        except (TypeError, ValueError):
            size = -1
        errors.extend(path_errors)
        if not _valid_snapshot_id(digest):
            errors.append(f"item_hash_invalid:{path}")
        if size < 0:
            errors.append(f"item_size_invalid:{path}")
        if not path or path in {row.get("path") for row in rows}:
            errors.append(f"item_path_duplicate_or_empty:{path}")
        rows.append(
            {
                "path": path,
                "bytes": size,
                "sha256": digest,
                "artifact_class": str(raw.get("artifact_class") or "unknown").strip(),
            }
        )
    rows.sort(key=lambda row: str(row["path"]).casefold())
    return rows, errors


def make_snapshot_manifest(
    items: Iterable[Mapping[str, Any]],
    *,
    trigger: str,
    created_at: str,
    parent_snapshot: str | None = None,
    catalog_items: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a deterministic manifest from supplied file evidence."""
    copied, errors = _item_rows(items)
    catalog, catalog_errors = _item_rows(catalog_items)
    errors.extend("catalog:" + error for error in catalog_errors)
    if not str(trigger or "").strip():
        errors.append("trigger_is_empty")
    if not str(created_at or "").strip():
        errors.append("created_at_is_empty")
    parent = None if parent_snapshot is None else _snapshot_id(parent_snapshot)
    if parent is not None and not _valid_snapshot_id(parent):
        errors.append("parent_snapshot_invalid")
    payload = {
        "schema_version": "viv_backup_manifest_v1",
        "created_at": str(created_at).strip(),
        "trigger": str(trigger or "").strip(),
        "parent_snapshot": parent,
        "source_root": "L:/Continue/Viv",
        "policy": {
            "restore": "staged_then_approved",
            "transaction_failure_rollback": True,
            "immutable_objects": True,
        },
        "copied_items": copied,
        "catalog_only_items": catalog,
        "skipped_items": [],
    }
    digest = _digest(payload)
    manifest = {
        **payload,
        "snapshot_id": digest,
        "manifest_sha256": digest,
        **_flags(),
        "manifest_write_performed": False,
    }
    return _result(
        not errors and bool(copied),
        operation="snapshot_manifest_plan",
        state="READY_FOR_GOVERNED_EXECUTOR" if not errors and copied else "ABSTAIN",
        errors=errors if errors else (["snapshot_contains_no_items"] if not copied else []),
        manifest=manifest,
        snapshot_id=digest,
    )


def verify_manifest(manifest: Any) -> dict[str, Any]:
    """Verify a supplied planner manifest without reading its object store."""
    if not isinstance(manifest, Mapping):
        return _result(False, operation="manifest_verify", state="ABSTAIN", errors=["manifest_not_mapping"])
    fields = (
        "schema_version",
        "created_at",
        "trigger",
        "parent_snapshot",
        "source_root",
        "policy",
        "copied_items",
        "catalog_only_items",
        "skipped_items",
    )
    missing = [field for field in fields if field not in manifest]
    if missing:
        return _result(False, operation="manifest_verify", state="ABSTAIN", errors=["missing:" + field for field in missing])
    payload = {field: manifest[field] for field in fields}
    expected = _digest(payload)
    supplied = _snapshot_id(manifest.get("snapshot_id"))
    supplied_manifest = _snapshot_id(manifest.get("manifest_sha256"))
    errors: list[str] = []
    if supplied != expected:
        errors.append("snapshot_id_mismatch")
    if supplied_manifest != expected:
        errors.append("manifest_hash_mismatch")
    return _result(
        not errors,
        operation="manifest_verify",
        state="VERIFIED" if not errors else "ABSTAIN",
        expected_sha256=expected,
        supplied_snapshot_id=supplied or None,
        supplied_manifest_sha256=supplied_manifest or None,
        errors=errors,
    )


def plan_snapshot(
    *,
    trigger: str,
    source_paths: Iterable[str],
    catalog_paths: Iterable[str] = (),
    allowed_roots: Iterable[str] = DEFAULT_ALLOWED_ROOTS,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    """Validate snapshot intent without scanning, hashing, or copying files."""
    errors: list[str] = []
    sources: list[str] = []
    catalog: list[str] = []
    for raw in list(source_paths)[:MAX_ITEMS]:
        path, path_errors = _path(raw, allowed_roots=allowed_roots)
        errors.extend(path_errors)
        sources.append(path)
    for raw in list(catalog_paths)[:MAX_ITEMS]:
        path, path_errors = _path(raw, allowed_roots=allowed_roots)
        errors.extend("catalog:" + error for error in path_errors)
        catalog.append(path)
    if not sources:
        errors.append("source_paths_empty")
    if max_bytes is not None:
        try:
            if int(max_bytes) <= 0:
                errors.append("max_bytes_invalid")
        except (TypeError, ValueError):
            errors.append("max_bytes_invalid")
    return _result(
        not errors,
        operation="snapshot_intent_plan",
        state="READY_FOR_GOVERNED_EXECUTOR" if not errors else "ABSTAIN",
        trigger=str(trigger or "").strip(),
        source_paths=sorted(set(sources), key=str.casefold),
        catalog_paths=sorted(set(catalog), key=str.casefold),
        errors=errors,
        execution_approved=False,
        security_authorization_requested=False,
        note="The governed backup executor must independently revalidate and hash real files.",
    )


def plan_restore(
    snapshot_id: str,
    items: Iterable[Mapping[str, Any]],
    *,
    allowed_root: str = "L:/Continue/Viv",
) -> dict[str, Any]:
    """Plan staged restore targets; never writes or commits live files."""
    errors: list[str] = []
    selected = _snapshot_id(snapshot_id)
    if not _valid_snapshot_id(selected):
        errors.append("snapshot_id_invalid")
    rows: list[dict[str, Any]] = []
    for raw in list(items)[:MAX_ITEMS]:
        if not isinstance(raw, Mapping):
            errors.append("restore_item_not_mapping")
            continue
        target, target_errors = _path(raw.get("target_path"), allowed_roots=(allowed_root,))
        errors.extend(target_errors)
        if "/artifacts/auto/backup_core/" in target.casefold():
            errors.append("restore_target_is_backup_vault")
        digest = _snapshot_id(raw.get("sha256"))
        if not _valid_snapshot_id(digest):
            errors.append(f"restore_hash_invalid:{target}")
        rows.append(
            {
                "target_path": target,
                "sha256": digest,
                "expected_current_sha256": _snapshot_id(raw.get("expected_current_sha256")) or None,
            }
        )
    if not rows:
        errors.append("restore_items_empty")
    return _result(
        not errors,
        operation="restore_plan",
        state="READY_FOR_ARCHITECT_APPROVAL" if not errors else "ABSTAIN",
        snapshot_id=selected,
        items=rows,
        errors=errors,
        stage_only=True,
        architect_approval_required=True,
        live_commit_approved=False,
    )


def plan_retention(manifests: Iterable[Mapping[str, Any]], *, keep: int = 7) -> dict[str, Any]:
    """Identify old supplied manifests without deleting or moving anything."""
    errors: list[str] = []
    try:
        keep_n = int(keep)
    except (TypeError, ValueError):
        keep_n = 0
        errors.append("keep_invalid")
    if not 1 <= keep_n <= MAX_RETENTION:
        errors.append("keep_out_of_range")
    rows: list[dict[str, Any]] = []
    for raw in list(manifests)[:MAX_RETENTION]:
        if not isinstance(raw, Mapping):
            errors.append("manifest_row_not_mapping")
            continue
        snapshot_id = _snapshot_id(raw.get("snapshot_id"))
        if not _valid_snapshot_id(snapshot_id):
            errors.append("manifest_snapshot_id_invalid")
            continue
        rows.append({"snapshot_id": snapshot_id, "created_at": str(raw.get("created_at") or "")})
    rows.sort(key=lambda row: (row["created_at"], row["snapshot_id"]), reverse=True)
    retained = rows[:keep_n] if not errors else []
    candidates = rows[keep_n:] if not errors else []
    return _result(
        not errors,
        operation="retention_plan",
        state="READY_FOR_GOVERNED_EXECUTOR" if not errors else "ABSTAIN",
        keep=keep_n,
        supplied_count=len(rows),
        retained=retained,
        deletion_candidates=candidates,
        deletion_performed=False,
        errors=errors,
    )


def module_status() -> dict[str, Any]:
    return {
        "ok": True,
        "module": MODULE_ID,
        "version": VERSION,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
        "implemented": [
            "snapshot_intent_validation",
            "content_addressed_manifest_building_and_verification",
            "staged_restore_target_planning",
            "retention_candidate_planning",
        ],
        "governed_executor": "lib.backup_core",
        "not_implemented": [
            "filesystem_scan_or_hash",
            "object_store_write",
            "restore_stage_write",
            "live_restore_commit",
            "deletion_or_rotation",
            "security_authorization_request",
            "llm_authority",
        ],
        **_flags(),
    }


__all__ = [
    "make_snapshot_manifest",
    "module_status",
    "plan_restore",
    "plan_retention",
    "plan_snapshot",
    "verify_manifest",
]
