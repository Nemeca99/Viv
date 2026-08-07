"""Deterministic CPU planning primitives for the AIOS ``data_core``.

The historical data core combines storage creation, imports, exports, cleanup,
database maintenance, and optional Rust execution.  This first Viv slice
ports the inspectable contract only: records have a stable schema and hash,
manifests preserve provenance, statistics are derived from supplied records,
cleanup is planned rather than executed, and recovery reports drift without
restoring anything.  Durable writes remain separately governed by backup and
security executors.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.4 data_core"
SOURCE_ROOT = "F:/AIOS_Clean/data_core"
RECORD_VERSION = "data_record_v1"
MANIFEST_VERSION = "data_manifest_v1"
DEFAULT_RETENTION_DAYS = 365
MAX_RECORDS = 10_000
SUPPORTED_EXPORT_FORMATS = ("json", "jsonl", "csv", "txt")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _record_without_hash(record: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in record.items() if str(key) != "sha256"}


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_text(value: Any) -> str:
    parsed = _parse_utc(value)
    if parsed is None:
        return ""
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_record(
    payload: Any,
    *,
    record_id: str,
    record_type: str = "unknown",
    source: str = "unknown",
    provenance: str = "unspecified",
    created_utc: str | None = None,
) -> dict[str, Any]:
    """Create a content-addressed record without writing it anywhere."""
    timestamp = (
        _utc_text(created_utc)
        if created_utc is not None
        else datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    record = {
        "record_version": RECORD_VERSION,
        "record_id": str(record_id).strip(),
        "record_type": str(record_type).strip(),
        "source": str(source).strip(),
        "provenance": str(provenance).strip(),
        "created_utc": timestamp,
        "payload": payload,
    }
    record["sha256"] = _digest(record)
    return record


def validate_record(
    record: Mapping[str, Any],
    *,
    expected_version: str = RECORD_VERSION,
) -> dict[str, Any]:
    """Validate schema, provenance, timestamp, and content hash."""
    if not isinstance(record, Mapping):
        return {"ok": False, "state": "ABSTAIN", "reason": "record_not_mapping"}
    version = str(record.get("record_version") or "")
    if version != expected_version:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "record_version_mismatch",
            "expected_version": expected_version,
            "supplied_version": version or None,
        }

    missing = [
        key
        for key in (
            "record_id",
            "record_type",
            "source",
            "provenance",
            "created_utc",
            "payload",
            "sha256",
        )
        if key not in record
    ]
    if missing:
        return {"ok": False, "state": "ABSTAIN", "reason": "record_fields_missing", "missing": missing}

    record_id = str(record.get("record_id") or "").strip()
    record_type = str(record.get("record_type") or "").strip()
    source = str(record.get("source") or "").strip()
    provenance = str(record.get("provenance") or "").strip()
    created_utc = _utc_text(record.get("created_utc"))
    if not record_id or not record_type or not source or not provenance:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "record_identity_or_provenance_empty",
            "record_id": record_id or None,
        }
    if not created_utc:
        return {"ok": False, "state": "ABSTAIN", "reason": "record_timestamp_invalid", "record_id": record_id}

    expected_hash = _digest(_record_without_hash(record))
    supplied_hash = str(record.get("sha256") or "").strip().casefold()
    if supplied_hash != expected_hash:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "record_hash_mismatch",
            "record_id": record_id,
            "expected_sha256": expected_hash,
            "supplied_sha256": supplied_hash or None,
        }
    return {
        "ok": True,
        "state": "VERIFIED",
        "record_id": record_id,
        "record_type": record_type,
        "source": source,
        "provenance": provenance,
        "created_utc": created_utc,
        "sha256": expected_hash,
        "record_version": version,
        "writes_performed": False,
        "llm_authority": False,
    }


def _manifest_entries(records: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    rows = list(records)
    for raw in rows[:MAX_RECORDS]:
        validation = validate_record(raw)
        if not validation.get("ok"):
            invalid.append(validation)
            continue
        entries.append(
            {
                "record_id": validation["record_id"],
                "record_type": validation["record_type"],
                "source": validation["source"],
                "provenance": validation["provenance"],
                "created_utc": validation["created_utc"],
                "sha256": validation["sha256"],
                "record_version": validation["record_version"],
            }
        )
    entries.sort(key=lambda row: (str(row["record_id"]), str(row["sha256"])))
    return entries, invalid


def _manifest_digest(entries: Iterable[Mapping[str, Any]]) -> str:
    return _digest({"manifest_version": MANIFEST_VERSION, "entries": list(entries)})


def build_manifest(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a stable provenance manifest from supplied records."""
    rows = list(records)
    entries, invalid = _manifest_entries(rows)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "record_count": len(entries),
        "invalid_record_count": len(invalid),
        "entries": entries,
    }
    manifest["manifest_sha256"] = _manifest_digest(entries)
    return {
        "ok": True,
        "state": "VERIFIED" if not invalid else "PARTIAL",
        "manifest": manifest,
        "accepted_count": len(entries),
        "rejected_count": len(invalid),
        "rejected": invalid,
        "truncated": len(rows) > MAX_RECORDS,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
    }


def storage_stats(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Calculate supplied-record statistics; no filesystem scan is performed."""
    type_counts: dict[str, int] = defaultdict(int)
    type_bytes: dict[str, int] = defaultdict(int)
    source_counts: dict[str, int] = defaultdict(int)
    total_bytes = 0
    accepted = 0
    rejected = 0
    for raw in records:
        validation = validate_record(raw)
        if not validation.get("ok"):
            rejected += 1
            continue
        size = len(_canonical_bytes(raw))
        record_type = validation["record_type"]
        source = validation["source"]
        accepted += 1
        total_bytes += size
        type_counts[record_type] += 1
        type_bytes[record_type] += size
        source_counts[source] += 1
    return {
        "ok": True,
        "state": "MEASURED_FROM_SUPPLIED_RECORDS",
        "record_count": accepted,
        "rejected_count": rejected,
        "estimated_serialized_bytes": total_bytes,
        "by_record_type": {
            key: {"count": type_counts[key], "estimated_serialized_bytes": type_bytes[key]}
            for key in sorted(type_counts)
        },
        "by_source": dict(sorted(source_counts.items())),
        "filesystem_scan_performed": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def plan_import(records: Iterable[Mapping[str, Any]], *, source: str) -> dict[str, Any]:
    """Validate an import batch and hand off a write-free commit plan."""
    manifest = build_manifest(records)
    accepted = int(manifest["accepted_count"])
    rejected = int(manifest["rejected_count"])
    state = "PLANNED" if accepted and not rejected else ("HOLD" if rejected else "NOTHING_TO_IMPORT")
    return {
        "ok": True,
        "state": state,
        "reason": "validated_import_batch" if state == "PLANNED" else "invalid_records_require_review" if state == "HOLD" else "empty_import_batch",
        "source": str(source),
        "manifest": manifest["manifest"],
        "accepted_count": accepted,
        "rejected_count": rejected,
        "requires_explicit_commit": True,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
    }


def plan_export(records: Iterable[Mapping[str, Any]], *, target_format: str = "json") -> dict[str, Any]:
    """Prepare a provenance-preserving export plan without creating a file."""
    export_format = str(target_format or "").strip().casefold()
    if export_format not in SUPPORTED_EXPORT_FORMATS:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "unsupported_export_format",
            "target_format": export_format or None,
            "supported_formats": list(SUPPORTED_EXPORT_FORMATS),
            "writes_performed": False,
        }
    manifest = build_manifest(records)
    return {
        "ok": True,
        "state": "PLANNED" if manifest["accepted_count"] else "NOTHING_TO_EXPORT",
        "target_format": export_format,
        "manifest": manifest["manifest"],
        "accepted_count": manifest["accepted_count"],
        "rejected_count": manifest["rejected_count"],
        "provenance_included": True,
        "requires_explicit_commit": True,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
    }


def plan_cleanup(
    records: Iterable[Mapping[str, Any]],
    *,
    now_utc: str,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    auto_cleanup_enabled: bool = False,
    explicit_commit: bool = False,
) -> dict[str, Any]:
    """Identify retention candidates without deleting or mutating records."""
    now = _parse_utc(now_utc)
    if now is None:
        return {"ok": False, "state": "ABSTAIN", "reason": "now_timestamp_invalid", "writes_performed": False}
    retention = max(0, int(retention_days))
    cutoff_seconds = retention * 86_400
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    future_dated = 0
    for raw in records:
        validation = validate_record(raw)
        if not validation.get("ok"):
            rejected.append(validation)
            continue
        created = _parse_utc(validation["created_utc"])
        assert created is not None
        age_seconds = (now - created).total_seconds()
        if age_seconds < 0:
            future_dated += 1
            continue
        if age_seconds >= cutoff_seconds:
            candidates.append(
                {
                    "record_id": validation["record_id"],
                    "sha256": validation["sha256"],
                    "created_utc": validation["created_utc"],
                    "age_days": round(age_seconds / 86_400, 6),
                }
            )

    if not candidates:
        state = "NO_CANDIDATES"
        reason = "retention_window_clear"
    elif not auto_cleanup_enabled:
        state = "HOLD"
        reason = "automatic_cleanup_disabled"
    elif not explicit_commit:
        state = "HOLD"
        reason = "explicit_cleanup_commit_required"
    else:
        state = "READY_FOR_GOVERNED_EXECUTOR"
        reason = "cleanup_candidates_ready_for_handoff"
    return {
        "ok": True,
        "state": state,
        "reason": reason,
        "now_utc": _utc_text(now_utc),
        "retention_days": retention,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "rejected_count": len(rejected),
        "future_dated_count": future_dated,
        "dry_run": True,
        "backup_before_cleanup": True,
        "delete_performed": False,
        "writes_performed": False,
        "execution_performed": False,
        "requires_governed_executor": bool(candidates),
        "llm_authority": False,
    }


def recovery_plan(expected_manifest: Mapping[str, Any], observed_records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare an expected manifest with observed records and report drift."""
    if not isinstance(expected_manifest, Mapping):
        return {"ok": False, "state": "ABSTAIN", "reason": "expected_manifest_not_mapping", "restore_performed": False}
    expected_version = str(expected_manifest.get("manifest_version") or "")
    expected_entries = expected_manifest.get("entries")
    supplied_digest = str(expected_manifest.get("manifest_sha256") or "").strip().casefold()
    if expected_version != MANIFEST_VERSION or not isinstance(expected_entries, list):
        return {"ok": False, "state": "ABSTAIN", "reason": "expected_manifest_invalid", "restore_performed": False}
    if supplied_digest != _manifest_digest(expected_entries):
        return {"ok": False, "state": "ABSTAIN", "reason": "expected_manifest_hash_mismatch", "restore_performed": False}

    observed = build_manifest(observed_records)
    expected_by_id = {str(row.get("record_id")): row for row in expected_entries if isinstance(row, Mapping)}
    observed_manifest = observed["manifest"]
    observed_by_id = {str(row.get("record_id")): row for row in observed_manifest["entries"]}
    missing = sorted(set(expected_by_id) - set(observed_by_id))
    unexpected = sorted(set(observed_by_id) - set(expected_by_id))
    changed = sorted(
        record_id
        for record_id in set(expected_by_id).intersection(observed_by_id)
        if str(expected_by_id[record_id].get("sha256")) != str(observed_by_id[record_id].get("sha256"))
    )
    drift = bool(missing or unexpected or changed or observed["rejected_count"])
    return {
        "ok": True,
        "state": "DRIFT" if drift else "VERIFIED",
        "reason": "manifest_matches_observed_records" if not drift else "manifest_drift_detected",
        "missing_record_ids": missing,
        "unexpected_record_ids": unexpected,
        "changed_record_ids": changed,
        "observed_rejected_count": observed["rejected_count"],
        "restore_plan": "governed_backup_restore_required" if drift else "none",
        "restore_authorized": False,
        "restore_performed": False,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
    }


def module_status() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "data_core",
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
        "implemented": [
            "content_addressed_record_schema",
            "provenance_preserving_manifest_planning",
            "supplied_record_storage_statistics",
            "import_and_export_planning",
            "retention_cleanup_planning",
            "manifest_recovery_drift_detection",
        ],
        "not_implemented": [
            "durable_import_write",
            "durable_export_write",
            "automatic_cleanup_or_delete",
            "database_vacuum_or_reindex",
            "backup_restore_commit",
            "llm_or_rust_data_authority",
        ],
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
    }
