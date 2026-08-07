"""Deterministic CPU planning primitives for the AIOS ``dream_core``.

The source dream implementation combines scheduling, memory mutation, random
meditation, heartbeat loops, and model calls.  This module ports the
inspectable boundary first.  It plans when a cycle is eligible, describes the
four documented phases, identifies bounded lexical consolidation candidates,
and prepares an append-only archive package.  It never reads or writes live
memory, starts a loop, calls a model, or claims that a projected improvement
was measured.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Iterable, Mapping

from lib.cpu_dream_planner import HOT_PULSE_BPM, MIN_SN


MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.3 dream_core"
SOURCE_ROOT = "F:/AIOS_Clean/dream_core"
PULSE_INTERVAL_SECONDS = 600
DEFAULT_INTERVAL_HOURS = 24.0
DEFAULT_FRAGMENT_THRESHOLD = 100
DEFAULT_MIN_IDLE_MINUTES = 5.0
DEFAULT_LEXICAL_THRESHOLD = 0.80
MAX_RECORDS = 200
MAX_PAIRS = 2_000
_TOKEN = re.compile(r"[a-z0-9_]{2,}")


def _bounded_float(value: Any, *, low: float = 0.0, high: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(number, high))


def _nonnegative(value: Any, *, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(str(text).casefold()))


def _normalized_text(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


def _record_text(record: Mapping[str, Any]) -> str:
    for key in ("text", "content", "body", "value"):
        value = record.get(key)
        if value is not None:
            return str(value)
    return ""


def _record_id(record: Mapping[str, Any], index: int) -> str:
    for key in ("id", "record_id", "file_id", "name"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return f"record-{index:04d}"


def _phase_rows(*, allowed: bool, mode: str) -> list[dict[str, Any]]:
    phase_specs = (
        ("light_scan", "read supplied fragments and identify candidates"),
        ("deep_consolidation", "prepare deterministic merges without committing them"),
        ("rem_pattern_review", "report lexical recurrence without inventing semantic claims"),
        ("awakening_index_review", "describe index and archive work for a governed executor"),
    )
    return [
        {
            "phase": name,
            "description": description,
            "state": "PLANNED" if allowed else "NOT_RUN",
            "mode": mode,
            "execution_performed": False,
            "writes_performed": False,
            "llm_authority": False,
        }
        for name, description in phase_specs
    ]


def plan_trigger(
    *,
    enabled: bool = True,
    active_conversation: bool = False,
    idle_minutes: float = 0.0,
    fragments_since_last: int = 0,
    hours_since_last: float = 0.0,
    manual_request: bool = False,
    pulse_elapsed_seconds: float = 0.0,
    pulse_bpm: float | None = None,
    run_during_idle: bool = True,
    minimum_idle_minutes: float = DEFAULT_MIN_IDLE_MINUTES,
    auto_trigger_interval_hours: float = DEFAULT_INTERVAL_HOURS,
    auto_trigger_fragment_count: int = DEFAULT_FRAGMENT_THRESHOLD,
    s_n: float | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Plan eligibility without starting a dream cycle or mutating state."""
    idle = _nonnegative(idle_minutes)
    fragments = max(0, int(fragments_since_last))
    hours = _nonnegative(hours_since_last)
    pulse_elapsed = _nonnegative(pulse_elapsed_seconds)
    min_idle = _nonnegative(minimum_idle_minutes, default=DEFAULT_MIN_IDLE_MINUTES)
    interval = _nonnegative(auto_trigger_interval_hours, default=DEFAULT_INTERVAL_HOURS)
    fragment_limit = max(1, int(auto_trigger_fragment_count))
    reasons: list[str] = []

    if not enabled:
        return {
            "ok": True,
            "state": "ABSTAIN",
            "reason": "disabled",
            "trigger_reasons": [],
            "mode": "none",
            "phases": _phase_rows(allowed=False, mode="none"),
            "writes_performed": False,
            "execution_performed": False,
            "llm_authority": False,
            "manual_source": SOURCE_ROOT,
        }

    if active_conversation and not manual_request and not force:
        return {
            "ok": True,
            "state": "HOLD",
            "reason": "active_conversation",
            "trigger_reasons": [],
            "mode": "none",
            "phases": _phase_rows(allowed=False, mode="none"),
            "writes_performed": False,
            "execution_performed": False,
            "llm_authority": False,
            "manual_source": SOURCE_ROOT,
        }

    if s_n is not None and _bounded_float(s_n) < MIN_SN and not force:
        return {
            "ok": True,
            "state": "HOLD",
            "reason": "s_n_dormancy",
            "trigger_reasons": [],
            "mode": "none",
            "s_n": _bounded_float(s_n),
            "phases": _phase_rows(allowed=False, mode="none"),
            "writes_performed": False,
            "execution_performed": False,
            "llm_authority": False,
            "manual_source": SOURCE_ROOT,
        }

    if manual_request or force:
        reasons.append("manual_request" if manual_request else "forced")
    if fragments >= fragment_limit:
        reasons.append("fragment_threshold")
    if interval > 0.0 and hours >= interval:
        reasons.append("interval_elapsed")
    if run_during_idle and idle >= min_idle:
        reasons.append("idle_window")
    if pulse_elapsed >= PULSE_INTERVAL_SECONDS:
        reasons.append("heartbeat_pulse")

    if not reasons:
        return {
            "ok": True,
            "state": "NOT_DUE",
            "reason": "no_trigger_due",
            "trigger_reasons": [],
            "mode": "none",
            "phases": _phase_rows(allowed=False, mode="none"),
            "writes_performed": False,
            "execution_performed": False,
            "llm_authority": False,
            "manual_source": SOURCE_ROOT,
        }

    pulse = None if pulse_bpm is None else _nonnegative(pulse_bpm)
    mode = "hot_path" if pulse is not None and pulse >= HOT_PULSE_BPM else "cold_path"
    return {
        "ok": True,
        "state": "PLANNED",
        "reason": reasons[0],
        "trigger_reasons": reasons,
        "mode": mode,
        "s_n": None if s_n is None else _bounded_float(s_n),
        "idle_minutes": idle,
        "fragments_since_last": fragments,
        "hours_since_last": hours,
        "pulse_elapsed_seconds": pulse_elapsed,
        "phases": _phase_rows(allowed=True, mode=mode),
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
        "manual_source": SOURCE_ROOT,
    }


def scan_fragments(
    records: Iterable[Mapping[str, Any]],
    *,
    lexical_threshold: float = DEFAULT_LEXICAL_THRESHOLD,
    max_records: int = MAX_RECORDS,
) -> dict[str, Any]:
    """Produce bounded exact/lexical candidate metadata from supplied records.

    Lexical overlap is deliberately not called semantic similarity.  A later
    governed component may approve a merge, but this function only reports
    candidates and preserves the input identifiers and provenance.
    """
    threshold = _bounded_float(lexical_threshold, low=0.0, high=1.0)
    limit = max(1, min(int(max_records), MAX_RECORDS))
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for index, raw in enumerate(records):
        if len(accepted) >= limit:
            break
        if not isinstance(raw, Mapping):
            rejected += 1
            continue
        text = _normalized_text(_record_text(raw))
        if not text:
            rejected += 1
            continue
        tokens = _tokens(text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        accepted.append(
            {
                "id": _record_id(raw, index),
                "sha256_16": digest,
                "token_count": len(tokens),
                "provenance": str(raw.get("provenance", "unknown")),
                "tokens": tokens,
            }
        )

    by_digest: dict[str, list[str]] = defaultdict(list)
    for row in accepted:
        by_digest[row["sha256_16"]].append(row["id"])
    duplicate_groups = [
        {"sha256_16": digest, "record_ids": sorted(ids), "count": len(ids)}
        for digest, ids in sorted(by_digest.items())
        if len(ids) > 1
    ]

    pairs: list[dict[str, Any]] = []
    for index, left in enumerate(accepted):
        for right in accepted[index + 1 :]:
            if len(pairs) >= MAX_PAIRS:
                break
            left_tokens = left["tokens"]
            right_tokens = right["tokens"]
            union = left_tokens | right_tokens
            similarity = (len(left_tokens & right_tokens) / len(union)) if union else 0.0
            if similarity >= threshold and left["sha256_16"] != right["sha256_16"]:
                pairs.append(
                    {
                        "left_id": left["id"],
                        "right_id": right["id"],
                        "lexical_jaccard": round(similarity, 6),
                        "candidate_kind": "lexical_overlap",
                    }
                )
        if len(pairs) >= MAX_PAIRS:
            break

    public_rows = [
        {key: value for key, value in row.items() if key != "tokens"}
        for row in accepted
    ]
    return {
        "ok": True,
        "state": "SCANNED",
        "records": public_rows,
        "accepted_count": len(accepted),
        "rejected_count": rejected,
        "truncated": len(accepted) >= limit,
        "duplicate_groups": duplicate_groups,
        "lexical_candidates": pairs,
        "lexical_threshold": threshold,
        "semantic_merges_performed": False,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
        "manual_source": SOURCE_ROOT,
    }


def archive_plan(scan: Mapping[str, Any]) -> dict[str, Any]:
    """Plan an append-only snapshot; never plan deletion or overwrite."""
    if not isinstance(scan, Mapping) or scan.get("state") != "SCANNED":
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "scan_not_verified",
            "writes_performed": False,
            "execution_performed": False,
            "llm_authority": False,
        }
    ids = [str(row.get("id")) for row in scan.get("records") or [] if isinstance(row, Mapping)]
    return {
        "ok": True,
        "state": "PLANNED",
        "operation": "append_snapshot",
        "record_ids": ids,
        "requires_explicit_commit": True,
        "delete_source_records": False,
        "overwrite_existing_archive": False,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
        "manual_source": SOURCE_ROOT,
    }


def metrics(scan: Mapping[str, Any]) -> dict[str, Any]:
    """Report source counts and projections without claiming an improvement."""
    if not isinstance(scan, Mapping) or scan.get("state") != "SCANNED":
        return {"ok": False, "state": "ABSTAIN", "reason": "scan_not_verified"}
    duplicate_reduction = sum(max(0, int(group.get("count", 0)) - 1) for group in scan.get("duplicate_groups") or [])
    accepted = int(scan.get("accepted_count", 0))
    return {
        "ok": True,
        "state": "PROJECTED",
        "input_records": accepted,
        "duplicate_groups": len(scan.get("duplicate_groups") or []),
        "lexical_candidates": len(scan.get("lexical_candidates") or []),
        "projected_exact_dedup_records": max(0, accepted - duplicate_reduction),
        "measured_improvement": False,
        "benchmark_required": True,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
    }


def module_status() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "dream_core",
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
        "implemented": [
            "deterministic_trigger_planning",
            "documented_phase_planning",
            "bounded_exact_and_lexical_candidate_scan",
            "append_only_archive_planning",
            "projection_metrics_without_improvement_claims",
        ],
        "not_implemented": [
            "automatic_background_loop",
            "semantic_summary_generation",
            "durable_memory_commit",
            "random_meditation",
            "LLM_dream_authority",
        ],
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
    }

