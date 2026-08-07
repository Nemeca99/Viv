"""Deterministic CPU diagnostics for the AIOS ``support_core`` boundary.

The historical support core combines health polling, logging, cache and
embedding operations, recovery, security helpers, and mutable backup calls.
This Viv slice evaluates supplied evidence only.  It aggregates health
checks, validates content-addressed cache entries, redacts common PII in a
derived copy, and prepares a diagnostic packet.  It does not start workers,
probe the network, touch a cache, write logs, or recover anything.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Iterable, Mapping


MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.5 support_core"
SOURCE_ROOT = "F:/AIOS_Clean/support_core"
MAX_CHECKS = 128
MAX_CACHE_ENTRIES = 2_000

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d().\- ]{7,}\d)(?!\d)")


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().casefold()
    if text in {"true", "yes", "ok", "pass", "healthy", "1"}:
        return True
    if text in {"false", "no", "fail", "failed", "critical", "0"}:
        return False
    return default


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def health_summary(checks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate caller-supplied health observations without probing live state."""
    rows: list[dict[str, Any]] = []
    rejected = 0
    for raw in list(checks)[:MAX_CHECKS]:
        if not isinstance(raw, Mapping):
            rejected += 1
            continue
        name = str(raw.get("name") or raw.get("id") or "").strip()
        if not name:
            rejected += 1
            continue
        ok = _as_bool(raw.get("ok"), default=str(raw.get("status") or "").casefold() in {"ok", "pass", "healthy"})
        rows.append(
            {
                "name": name,
                "ok": ok,
                "critical": _as_bool(raw.get("critical")),
                "detail": str(raw.get("detail") or raw.get("message") or ""),
            }
        )
    if not rows:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "no_valid_health_checks",
            "checks": [],
            "rejected_count": rejected,
            "live_probe_performed": False,
            "writes_performed": False,
            "llm_authority": False,
        }
    failed = [row for row in rows if not row["ok"]]
    critical = [row for row in failed if row["critical"]]
    state = "CRITICAL" if critical else "DEGRADED" if failed else "HEALTHY"
    return {
        "ok": True,
        "state": state,
        "reason": "all_supplied_checks_passed" if not failed else "supplied_check_failures_present",
        "checks": rows,
        "check_count": len(rows),
        "failed_count": len(failed),
        "critical_failed_count": len(critical),
        "rejected_count": rejected,
        "live_probe_performed": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def make_cache_entry(
    payload: str,
    *,
    cache_id: str,
    source: str = "unknown",
    status: str = "active",
    hit: bool | None = None,
) -> dict[str, Any]:
    """Create a content-addressed cache fixture without persisting it."""
    text = str(payload)
    row: dict[str, Any] = {
        "cache_id": str(cache_id).strip(),
        "source": str(source).strip(),
        "status": str(status).strip().casefold(),
        "payload": text,
        "size_bytes": len(text.encode("utf-8")),
        "sha256": _sha256_text(text),
    }
    if hit is not None:
        row["hit"] = bool(hit)
    return row


def validate_cache_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Validate cache identity and content hash from supplied metadata."""
    if not isinstance(entry, Mapping):
        return {"ok": False, "state": "ABSTAIN", "reason": "cache_entry_not_mapping"}
    cache_id = str(entry.get("cache_id") or "").strip()
    source = str(entry.get("source") or "").strip()
    status = str(entry.get("status") or "").strip().casefold()
    payload = entry.get("payload")
    supplied_hash = str(entry.get("sha256") or "").strip().casefold()
    try:
        size_bytes = int(entry.get("size_bytes"))
    except (TypeError, ValueError):
        size_bytes = -1
    if not cache_id or not source or not status:
        return {"ok": False, "state": "ABSTAIN", "reason": "cache_identity_missing", "cache_id": cache_id or None}
    if not isinstance(payload, str):
        return {"ok": False, "state": "ABSTAIN", "reason": "cache_payload_missing", "cache_id": cache_id}
    expected_hash = _sha256_text(payload)
    expected_size = len(payload.encode("utf-8"))
    if supplied_hash != expected_hash:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "cache_hash_mismatch",
            "cache_id": cache_id,
            "expected_sha256": expected_hash,
            "supplied_sha256": supplied_hash or None,
        }
    if size_bytes != expected_size or size_bytes < 0:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "cache_size_mismatch",
            "cache_id": cache_id,
            "expected_size_bytes": expected_size,
            "supplied_size_bytes": size_bytes,
        }
    return {
        "ok": True,
        "state": "VERIFIED",
        "cache_id": cache_id,
        "source": source,
        "status": status,
        "size_bytes": size_bytes,
        "sha256": expected_hash,
        "hit": entry.get("hit") if isinstance(entry.get("hit"), bool) else None,
        "writes_performed": False,
        "llm_authority": False,
    }


def cache_summary(entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize supplied cache entries; no cache directory is scanned."""
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in list(entries)[:MAX_CACHE_ENTRIES]:
        validation = validate_cache_entry(raw)
        if validation.get("ok"):
            valid.append(validation)
        else:
            rejected.append(validation)
    by_status: dict[str, int] = defaultdict(int)
    hits = 0
    misses = 0
    for row in valid:
        by_status[str(row["status"])] += 1
        if row.get("hit") is True:
            hits += 1
        elif row.get("hit") is False:
            misses += 1
    observations = hits + misses
    return {
        "ok": True,
        "state": "EMPTY" if not valid and not rejected else "VERIFIED" if not rejected else "PARTIAL",
        "entry_count": len(valid),
        "rejected_count": len(rejected),
        "rejected": rejected,
        "total_size_bytes": sum(int(row["size_bytes"]) for row in valid),
        "by_status": dict(sorted(by_status.items())),
        "hits": hits,
        "misses": misses,
        "hit_rate": round(hits / observations, 6) if observations else None,
        "filesystem_scan_performed": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def redact_text(text: str) -> dict[str, Any]:
    """Return a deterministic redacted copy for logging or diagnostics."""
    original = str(text)
    redacted, email_count = _EMAIL.subn("[REDACTED_EMAIL]", original)
    redacted, phone_count = _PHONE.subn("[REDACTED_PHONE]", redacted)
    return {
        "ok": True,
        "text": redacted,
        "redactions": {"email": email_count, "phone": phone_count},
        "changed": redacted != original,
        "writes_performed": False,
        "llm_authority": False,
    }


def diagnostic_report(
    checks: Iterable[Mapping[str, Any]],
    cache_entries: Iterable[Mapping[str, Any]],
    *,
    sample_text: str | None = None,
) -> dict[str, Any]:
    """Combine supplied health, cache, and optional redaction evidence."""
    health = health_summary(checks)
    cache = cache_summary(cache_entries)
    redaction = redact_text(sample_text) if sample_text is not None else None
    ok = bool(health.get("ok")) and cache.get("state") in {"EMPTY", "VERIFIED"}
    state = health.get("state") if health.get("ok") else "ABSTAIN"
    return {
        "ok": ok,
        "state": state,
        "health": health,
        "cache": cache,
        "redaction": redaction,
        "diagnostic_authority": "supplied_evidence_only",
        "live_probe_performed": False,
        "filesystem_scan_performed": False,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
    }


def module_status() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "support_core",
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
        "implemented": [
            "supplied_health_check_aggregation",
            "content_addressed_cache_validation",
            "supplied_cache_statistics",
            "deterministic_email_and_phone_redaction",
            "diagnostic_packet_planning",
        ],
        "not_implemented": [
            "background_health_polling",
            "live_network_or_database_probes",
            "durable_log_write",
            "cache_mutation_or_recovery",
            "embedding_or_llm_authority",
        ],
        "live_probe_performed": False,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
    }
