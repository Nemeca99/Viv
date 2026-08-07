"""Deterministic CPU utility planning for the AIOS ``utils_core`` boundary.

The historical ``utils_core`` source combines validation with file writes,
subprocess bridges, mutable caches, monitoring, and recovery.  This first Viv
slice keeps the useful decision surfaces while closing effects:

* validate supplied values without reading or changing external state;
* calculate retry and freshness plans without sleeping or probing;
* classify paths and file operations without resolving the filesystem;
* build and verify content-addressed inter-core envelopes;
* describe Rust/PowerShell work without executing a bridge.

It is deliberately a CPU planner, not an executor.  The adapter may expose a
separate legacy read-mirror for inventory, but this module has no filesystem,
subprocess, network, cache, logging, or model authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


MODULE_ID = "utils_core"
VERSION = "v1"
MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.6 utils_core"
SOURCE_ROOT = "F:/AIOS_Clean/utils_core"

MAX_TEXT_LENGTH = 1_000_000
MAX_RETRIES = 16
MAX_DELAY_SECONDS = 86_400.0
READ_ONLY_OPERATIONS = frozenset({"inspect", "read", "hash", "plan"})
BRIDGES = frozenset({"rust", "powershell"})
_CORE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


def _canonical(value: Any) -> str:
    """Serialize a JSON-compatible value deterministically."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: Any) -> str:
    if isinstance(value, str):
        data = value.encode("utf-8")
    else:
        data = _canonical(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _flags() -> dict[str, bool]:
    return {
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "execution_performed": False,
        "network_probe_performed": False,
        "sleep_performed": False,
        "llm_authority": False,
    }


def _result(ok: bool, **fields: Any) -> dict[str, Any]:
    result = {"ok": bool(ok), **fields}
    result.update(_flags())
    return result


def validate_input(value: Any, *, kind: str = "json", max_length: int = MAX_TEXT_LENGTH) -> dict[str, Any]:
    """Validate a supplied value without coercing or persisting it.

    ``kind`` is intentionally small and explicit.  Validation reports a
    digest for accepted JSON/text values so callers can carry provenance
    without retaining the raw payload in an audit packet.
    """
    normalized_kind = str(kind or "").strip().casefold()
    errors: list[str] = []
    warnings: list[str] = []
    digest: str | None = None

    if normalized_kind == "json":
        try:
            digest = _sha256(value)
        except (TypeError, ValueError, OverflowError) as exc:
            errors.append(f"not_json_compatible:{type(exc).__name__}")
    elif normalized_kind == "text":
        if not isinstance(value, str):
            errors.append("text_must_be_string")
        else:
            if len(value) > max(0, int(max_length)):
                errors.append("text_exceeds_max_length")
            if not value.strip():
                warnings.append("text_is_empty")
            if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
                warnings.append("text_contains_control_character")
            digest = _sha256(value)
    elif normalized_kind == "record":
        if not isinstance(value, Mapping):
            errors.append("record_must_be_mapping")
        else:
            try:
                digest = _sha256(dict(value))
            except (TypeError, ValueError, OverflowError) as exc:
                errors.append(f"record_not_json_compatible:{type(exc).__name__}")
    elif normalized_kind == "path":
        path_result = classify_path(value)
        errors.extend(path_result.get("errors", []))
        warnings.extend(path_result.get("warnings", []))
        digest = path_result.get("path_sha256")
    else:
        errors.append("unsupported_validation_kind")

    return _result(
        not errors,
        kind=normalized_kind,
        errors=errors,
        warnings=warnings,
        digest=digest,
    )


def plan_retry(
    *,
    max_retries: int = 3,
    base_delay_seconds: float = 2.0,
    multiplier: float = 2.0,
    max_delay_seconds: float = 60.0,
    retryable: bool = True,
) -> dict[str, Any]:
    """Return a bounded retry schedule; never sleeps or retries an operation."""
    errors: list[str] = []
    try:
        retries = int(max_retries)
        base = float(base_delay_seconds)
        factor = float(multiplier)
        ceiling = float(max_delay_seconds)
    except (TypeError, ValueError):
        retries, base, factor, ceiling = 0, 0.0, 0.0, 0.0
        errors.append("retry_parameters_not_numeric")

    if not 0 <= retries <= MAX_RETRIES:
        errors.append("max_retries_out_of_range")
    if not math.isfinite(base) or not 0.0 <= base <= MAX_DELAY_SECONDS:
        errors.append("base_delay_out_of_range")
    if not math.isfinite(factor) or not 1.0 <= factor <= 16.0:
        errors.append("multiplier_out_of_range")
    if not math.isfinite(ceiling) or not 0.0 <= ceiling <= MAX_DELAY_SECONDS:
        errors.append("max_delay_out_of_range")

    delays: list[float] = []
    if not errors and bool(retryable):
        for attempt in range(retries):
            delay = min(ceiling, base * (factor**attempt))
            delays.append(round(delay, 6))
    return _result(
        not errors,
        operation="retry_plan",
        retryable=bool(retryable),
        max_retries=retries,
        attempts=1 + len(delays),
        delays_seconds=delays,
        errors=errors,
        execution_plan_only=True,
    )


def _normalize_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
    else:
        raise ValueError("timestamp_must_be_iso_string_or_datetime")
    if parsed.tzinfo is None:
        raise ValueError("timestamp_must_include_timezone")
    return parsed.astimezone(timezone.utc)


def timestamp_age(
    observed_at: str | datetime,
    now: str | datetime,
    *,
    stale_after_seconds: float = 3.0,
) -> dict[str, Any]:
    """Compare two caller-supplied timestamps without consulting the clock."""
    errors: list[str] = []
    try:
        observed = _normalize_timestamp(observed_at)
        current = _normalize_timestamp(now)
        threshold = float(stale_after_seconds)
        if not math.isfinite(threshold) or threshold < 0:
            raise ValueError("stale_after_seconds_out_of_range")
    except (TypeError, ValueError, OverflowError) as exc:
        errors.append(str(exc))
        return _result(False, operation="timestamp_age", errors=errors)

    age = (current - observed).total_seconds()
    return _result(
        True,
        operation="timestamp_age",
        observed_at=observed.isoformat().replace("+00:00", "Z"),
        now=current.isoformat().replace("+00:00", "Z"),
        age_seconds=round(age, 6),
        future_observation=age < 0,
        stale=age > threshold,
        stale_after_seconds=threshold,
        errors=[],
    )


def _normalized_path(path: Any) -> tuple[str | None, list[str]]:
    if not isinstance(path, str):
        return None, ["path_must_be_string"]
    raw = path.strip()
    if not raw:
        return None, ["path_is_empty"]
    if any(ord(char) < 32 for char in raw):
        return None, ["path_contains_control_character"]
    normalized = raw.replace("\\", "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized.rstrip("/") or "/", []


def classify_path(
    path: Any,
    *,
    allowed_roots: Iterable[str] = (),
    operation: str = "inspect",
) -> dict[str, Any]:
    """Classify a path string without resolving or touching the filesystem."""
    normalized, errors = _normalized_path(path)
    op = str(operation or "").strip().casefold()
    if op not in READ_ONLY_OPERATIONS:
        errors.append("effectful_operation_requires_runtime_gate")
    roots: list[str] = []
    for root in allowed_roots:
        normalized_root, root_errors = _normalized_path(root)
        if root_errors or normalized_root is None:
            errors.append("invalid_allowed_root")
        else:
            roots.append(normalized_root.rstrip("/").casefold())

    if normalized is None:
        normalized = ""
    folded = normalized.casefold()
    parts = [part for part in folded.split("/") if part]
    traversal = ".." in parts
    if traversal:
        errors.append("path_traversal_segment")

    under_root = not roots or any(folded == root or folded.startswith(root + "/") for root in roots)
    if roots and not under_root:
        errors.append("outside_declared_roots")

    return _result(
        not errors,
        operation="classify_path",
        requested_operation=op,
        path=normalized,
        absolute=bool(re.match(r"^[a-z]:/", folded) or folded.startswith("/")),
        under_declared_root=under_root,
        traversal_detected=traversal,
        errors=errors,
        warnings=[],
        path_sha256=_sha256(normalized),
        filesystem_resolved=False,
    )


def plan_file_operation(
    path: Any,
    *,
    operation: str = "inspect",
    allowed_roots: Iterable[str] = (),
) -> dict[str, Any]:
    """Prepare a file-operation decision without performing the operation."""
    classification = classify_path(path, allowed_roots=allowed_roots, operation=operation)
    return _result(
        bool(classification.get("ok")),
        operation="file_operation_plan",
        requested_operation=classification.get("requested_operation"),
        classification=classification,
        execution_approved=False,
        effect_performed=False,
        reason="read_only_plan_only",
    )


def make_message_envelope(
    source_core: str,
    target_core: str,
    message_type: str,
    data: Any,
    *,
    priority: int = 1,
    occurred_at: str | datetime | None = None,
    schema_version: str = "utils.message.v1",
) -> dict[str, Any]:
    """Build a deterministic, content-addressed inter-core envelope."""
    names = {
        "source_core": str(source_core or "").strip(),
        "target_core": str(target_core or "").strip(),
        "message_type": str(message_type or "").strip(),
    }
    if any(not _CORE_NAME.fullmatch(value) for value in names.values()):
        raise ValueError("core_names_or_message_type_invalid")
    if not isinstance(priority, int) or isinstance(priority, bool) or not 1 <= priority <= 10:
        raise ValueError("priority_out_of_range")
    payload: dict[str, Any] = {
        "schema_version": str(schema_version).strip() or "utils.message.v1",
        **names,
        "message_type": names["message_type"],
        "data": data,
        "priority": priority,
    }
    if occurred_at is not None:
        timestamp = _normalize_timestamp(occurred_at)
        payload["occurred_at"] = timestamp.isoformat().replace("+00:00", "Z")
    digest = _sha256(payload)
    return {
        "message_id": digest[:24],
        **payload,
        "sha256": digest,
    }


def validate_message_envelope(message: Any) -> dict[str, Any]:
    """Verify an envelope's required fields and content digest."""
    if not isinstance(message, Mapping):
        return _result(False, operation="message_validation", errors=["message_must_be_mapping"])
    required = ("message_id", "schema_version", "source_core", "target_core", "message_type", "data", "priority", "sha256")
    missing = [field for field in required if field not in message]
    if missing:
        return _result(False, operation="message_validation", errors=["missing:" + field for field in missing])
    payload = {key: message[key] for key in message if key not in {"message_id", "sha256"}}
    try:
        expected = _sha256(payload)
    except (TypeError, ValueError, OverflowError) as exc:
        return _result(False, operation="message_validation", errors=[f"payload_not_json_compatible:{type(exc).__name__}"])
    supplied = str(message.get("sha256") or "").casefold()
    message_id = str(message.get("message_id") or "")
    names_ok = all(_CORE_NAME.fullmatch(str(message.get(field) or "")) for field in ("source_core", "target_core", "message_type"))
    priority = message.get("priority")
    priority_ok = isinstance(priority, int) and not isinstance(priority, bool) and 1 <= priority <= 10
    ok = names_ok and priority_ok and supplied == expected and message_id == expected[:24]
    errors: list[str] = []
    if not names_ok:
        errors.append("core_names_or_message_type_invalid")
    if not priority_ok:
        errors.append("priority_out_of_range")
    if supplied != expected:
        errors.append("message_hash_mismatch")
    if message_id != expected[:24]:
        errors.append("message_id_mismatch")
    return _result(
        ok,
        operation="message_validation",
        message_id=message_id or None,
        expected_sha256=expected,
        supplied_sha256=supplied or None,
        errors=errors,
    )


def plan_bridge_call(bridge: str, action: str) -> dict[str, Any]:
    """Describe a bridge request while keeping execution closed."""
    bridge_name = str(bridge or "").strip().casefold()
    action_name = str(action or "").strip()
    errors: list[str] = []
    if bridge_name not in BRIDGES:
        errors.append("unsupported_bridge")
    if not action_name:
        errors.append("bridge_action_is_empty")
    return _result(
        not errors,
        operation="bridge_plan",
        bridge=bridge_name,
        action=action_name,
        errors=errors,
        execution_approved=False,
        reason="bridge_execution_requires_separate_runtime_gate",
    )


def module_status() -> dict[str, Any]:
    """Return the static capability and authority boundary."""
    return {
        "ok": True,
        "module": MODULE_ID,
        "version": VERSION,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
        "implemented": [
            "input_validation",
            "retry_schedule_planning",
            "explicit_timestamp_freshness",
            "path_classification_without_resolution",
            "content_addressed_message_envelopes",
            "bridge_call_planning_without_execution",
        ],
        "not_implemented": [
            "filesystem_read_or_write",
            "subprocess_or_rust_execution",
            "powershell_execution",
            "sleep_or_timeout_worker",
            "mutable_cache_or_provenance_logging",
            "network_probe",
            "llm_authority",
        ],
        **_flags(),
    }


__all__ = [
    "classify_path",
    "make_message_envelope",
    "module_status",
    "plan_bridge_call",
    "plan_file_operation",
    "plan_retry",
    "timestamp_age",
    "validate_input",
    "validate_message_envelope",
]
