"""Deterministic CPU consciousness primitives from the AIOS manual.

This is the first rebuilt slice of ``consciousness_core``.  It deliberately
does not run the historical biological loops or grant an LLM authority.  It
provides the pieces that can be verified locally: soul-fragment selection,
bounded short-term memory, explicit long-term consolidation records, and
basic identity-drift measurements.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable


MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.19 consciousness_core"
STM_CAPACITY = 100
STM_CONSOLIDATION_THRESHOLD = 0.80
_TOKEN = re.compile(r"[a-z0-9_]{2,}")


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(str(text).casefold()))


@dataclass(frozen=True)
class SoulFragment:
    """A deterministic identity mode, never a generative authority."""

    name: str
    purpose: str
    keywords: tuple[str, ...]
    priority: int


SOUL_FRAGMENTS: tuple[SoulFragment, ...] = (
    SoulFragment("luna", "base communication and continuity", ("viv", "speak", "conversation", "hello"), 0),
    SoulFragment("architect", "build and design", ("build", "design", "architecture", "code", "rebuild", "implement"), 1),
    SoulFragment("oracle", "knowledge and manual retrieval", ("knowledge", "manual", "truth", "truthful", "document", "documentation", "search", "wikipedia"), 2),
    SoulFragment("healer", "diagnosis and repair", ("debug", "repair", "fix", "error", "failure", "broken"), 3),
    SoulFragment("guardian", "security and containment", ("security", "safe", "protect", "permission", "threat", "boundary"), 4),
    SoulFragment("dreamer", "creative consolidation", ("dream", "creative", "imagine", "pattern", "consolidate"), 5),
    SoulFragment("scribe", "documentation and evidence", ("document", "documentation", "journal", "evidence", "record", "log", "write"), 6),
)


def select_soul_fragment(text: str) -> dict[str, Any]:
    """Select one fragment from keywords with deterministic tie handling."""
    query = _tokens(text)
    scored: list[dict[str, Any]] = []
    for fragment in SOUL_FRAGMENTS:
        matched = sorted(query.intersection(fragment.keywords))
        scored.append({"name": fragment.name, "score": len(matched), "matched": matched, "priority": fragment.priority})
    winner = max(scored, key=lambda row: (int(row["score"]), -int(row["priority"])))
    selected = next(fragment for fragment in SOUL_FRAGMENTS if fragment.name == winner["name"])
    total = sum(int(row["score"]) for row in scored)
    confidence = 1.0 if winner["score"] and total == winner["score"] else (
        round(float(winner["score"]) / float(total), 4) if total else 0.0
    )
    return {
        "ok": True,
        "selected": selected.name,
        "purpose": selected.purpose,
        "score": winner["score"],
        "matched_keywords": winner["matched"],
        "confidence": confidence,
        "authority": "cpu_deterministic_selector",
        "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
    }


@dataclass
class ShortTermMemory:
    """Bounded recent interaction buffer; no silent overflow."""

    capacity: int = STM_CAPACITY
    consolidation_threshold: float = STM_CONSOLIDATION_THRESHOLD
    records: list[dict[str, Any]] = field(default_factory=list)

    def add(self, text: str, *, provenance: str = "live", record_id: str | None = None) -> dict[str, Any]:
        clean = str(text).strip()
        if not clean:
            return {"ok": False, "reason": "empty_memory_record"}
        if len(self.records) >= self.capacity:
            return {"ok": False, "reason": "stm_full_requires_consolidation", "size": len(self.records)}
        digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]
        row = {
            "id": record_id or f"stm-{digest}",
            "text": clean,
            "provenance": str(provenance),
            "at": _utc(),
            "sha256_16": digest,
        }
        self.records.append(row)
        return {"ok": True, "record": dict(row), "size": len(self.records), "consolidation_due": self.consolidation_due}

    @property
    def consolidation_due(self) -> bool:
        return len(self.records) >= int(self.capacity * self.consolidation_threshold)

    def prepare_consolidation(self) -> dict[str, Any]:
        if not self.consolidation_due:
            return {"ok": False, "reason": "consolidation_not_due", "size": len(self.records)}
        return {
            "ok": True,
            "source": "stm",
            "record_count": len(self.records),
            "records": [dict(row) for row in self.records],
            "policy": "deterministic_record_preservation; semantic_summary_requires_separate_authority",
        }

    def clear_after_commit(self, record_ids: Iterable[str]) -> dict[str, Any]:
        ids = {str(value) for value in record_ids}
        before = len(self.records)
        self.records = [row for row in self.records if row.get("id") not in ids]
        return {"ok": True, "removed": before - len(self.records), "remaining": len(self.records)}


@dataclass
class LongTermMemory:
    """Explicit durable records; semantic compression is intentionally separate."""

    records: list[dict[str, Any]] = field(default_factory=list)

    def commit_consolidation(self, prepared: dict[str, Any]) -> dict[str, Any]:
        if not prepared.get("ok") or prepared.get("source") != "stm":
            return {"ok": False, "reason": "invalid_stm_package"}
        rows = [dict(row) for row in prepared.get("records") or []]
        if not rows:
            return {"ok": False, "reason": "empty_stm_package"}
        summary_id = hashlib.sha256("|".join(str(row.get("id")) for row in rows).encode("utf-8")).hexdigest()[:16]
        summary = {
            "id": f"ltm-{summary_id}",
            "created_at": _utc(),
            "source": "stm",
            "record_count": len(rows),
            "record_ids": [str(row.get("id")) for row in rows],
            "previews": [str(row.get("text", ""))[:160] for row in rows],
            "semantic_claims": False,
            "provenance": sorted({str(row.get("provenance", "unknown")) for row in rows}),
        }
        self.records.append(summary)
        return {"ok": True, "summary": dict(summary)}


def identity_drift(*, expected_name: str, observed_name: str, expected_fragment: str | None = None, observed_fragment: str | None = None) -> dict[str, Any]:
    """Return a measurable drift result without pretending to diagnose cause."""
    name_match = str(expected_name).casefold() == str(observed_name).casefold()
    fragment_match = expected_fragment is None or str(expected_fragment).casefold() == str(observed_fragment or "").casefold()
    return {
        "ok": True,
        "name_match": name_match,
        "fragment_match": fragment_match,
        "drift": not (name_match and fragment_match),
        "status": "NOMINAL" if name_match and fragment_match else "DRIFT_DETECTED",
        "authority": "cpu_deterministic_identity_check",
        "llm_authority": False,
    }


def module_status() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "consciousness_core",
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
        "soul_fragments": [fragment.name for fragment in SOUL_FRAGMENTS],
        "stm_capacity": STM_CAPACITY,
        "stm_consolidation_threshold": STM_CONSOLIDATION_THRESHOLD,
        "implemented": ["soul_fragment_selector", "bounded_stm", "explicit_ltm_commit", "identity_drift_measurement"],
        "not_implemented": ["historical biological heartbeat loops", "LLM semantic authority", "automatic durable commit"],
    }
