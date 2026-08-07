"""Deterministic CPU consciousness primitives from the AIOS manual.

This is the first rebuilt slice of ``consciousness_core``.  It deliberately
does not run the historical biological loops or grant an LLM authority.  It
provides the pieces that can be verified locally: soul-fragment selection,
bounded short-term memory, explicit long-term consolidation records, and
basic identity-drift measurements.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


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


@dataclass
class ReflectionGraph:
    """Bounded deterministic mirror graph; no language-model introspection."""

    nodes: dict[str, dict[str, float]] = field(default_factory=dict)
    edges: list[tuple[str, str, str]] = field(default_factory=list)
    reflection_count: int = 0
    compression_index: float = 0.0
    motive_coherence_index: float = 0.0

    def _merge_experience(self, experience: Mapping[str, Any]) -> dict[str, int]:
        rejected_nodes = 0
        rejected_edges = 0
        raw_nodes = experience.get("nodes") or {}
        if not isinstance(raw_nodes, Mapping):
            rejected_nodes += 1
            raw_nodes = {}
        for raw_name, raw_features in raw_nodes.items():
            name = str(raw_name).strip()
            if not name or not isinstance(raw_features, Mapping):
                rejected_nodes += 1
                continue
            target = self.nodes.setdefault(name, {})
            for raw_feature, raw_value in raw_features.items():
                feature = str(raw_feature).strip()
                if not feature or isinstance(raw_value, bool):
                    rejected_nodes += 1
                    continue
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    rejected_nodes += 1
                    continue
                if not math.isfinite(value):
                    rejected_nodes += 1
                    continue
                target[feature] = round(target.get(feature, 0.0) + value, 6)

        raw_edges = experience.get("edges") or []
        if not isinstance(raw_edges, (list, tuple)):
            rejected_edges += 1
            raw_edges = []
        for raw_edge in raw_edges:
            if not isinstance(raw_edge, (list, tuple)) or len(raw_edge) != 3:
                rejected_edges += 1
                continue
            edge = tuple(str(value).strip() for value in raw_edge)
            if not all(edge):
                rejected_edges += 1
                continue
            if edge not in self.edges:
                self.edges.append(edge)
        return {"rejected_nodes": rejected_nodes, "rejected_edges": rejected_edges}

    def _recompute_metrics(self) -> None:
        causal_count = sum(1 for _, label, _ in self.edges if label.casefold() == "causes")
        mechanism_targets: dict[str, set[str]] = {}
        for source, label, target in self.edges:
            if label.casefold() == "mechanism":
                mechanism_targets.setdefault(target, set()).add(source)
        mechanism_count = sum(len(values) for values in mechanism_targets.values())
        self.compression_index = round(mechanism_count / causal_count, 6) if causal_count else 0.0
        unified = sum(1 for values in mechanism_targets.values() if len(values) >= 2)
        self.motive_coherence_index = round(unified / max(1, len(mechanism_targets)), 6)

    def reflect(self, experience: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Merge one typed experience and return deterministic mirror metrics."""
        self.reflection_count += 1
        rejected = {"rejected_nodes": 0, "rejected_edges": 0}
        if experience is not None:
            if not isinstance(experience, Mapping):
                rejected = {"rejected_nodes": 1, "rejected_edges": 1}
            else:
                rejected = self._merge_experience(experience)
        self._recompute_metrics()
        return {
            "ok": rejected["rejected_nodes"] == 0 and rejected["rejected_edges"] == 0,
            "reflection_count": self.reflection_count,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "compression_index": self.compression_index,
            "motive_coherence_index": self.motive_coherence_index,
            **rejected,
            "authority": "cpu_deterministic_reflection_graph",
            "llm_authority": False,
        }

    def recent_patterns(self, limit: int = 5) -> list[str]:
        count = max(1, min(int(limit), 20))
        patterns: list[str] = []
        for source, label, target in reversed(self.edges):
            pattern = f"{source} {label} {target}"
            if pattern not in patterns:
                patterns.append(pattern)
            if len(patterns) >= count:
                break
        return patterns

    def state(self) -> dict[str, Any]:
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "reflection_count": self.reflection_count,
            "compression_index": self.compression_index,
            "motive_coherence_index": self.motive_coherence_index,
            "recent_patterns": self.recent_patterns(),
            "llm_authority": False,
        }


def consolidate_once(
    stm: ShortTermMemory,
    ltm: LongTermMemory,
    *,
    explicit_authorization: bool = False,
) -> dict[str, Any]:
    """Prepare or explicitly commit STM -> LTM without silent data loss."""
    prepared = stm.prepare_consolidation()
    base = {
        "writes_performed": False,
        "llm_authority": False,
        "explicit_authorization": bool(explicit_authorization),
    }
    if not prepared.get("ok"):
        return {"ok": True, "state": "NOT_DUE", "prepared": prepared, **base}
    if not explicit_authorization:
        return {
            "ok": True,
            "state": "HOLD",
            "reason": "explicit_memory_commit_authorization_required",
            "prepared": prepared,
            **base,
        }
    committed = ltm.commit_consolidation(prepared)
    if not committed.get("ok"):
        return {"ok": False, "state": "ABSTAIN", "reason": "ltm_commit_rejected", "commit": committed, **base}
    record_ids = [str(row.get("id")) for row in prepared.get("records") or []]
    cleared = stm.clear_after_commit(record_ids)
    if int(cleared.get("removed", 0)) != len(record_ids):
        return {
            "ok": False,
            "state": "INCONCLUSIVE",
            "reason": "stm_clear_count_mismatch",
            "commit": committed,
            "clear": cleared,
            **base,
        }
    return {
        "ok": True,
        "state": "COMMITTED_IN_MEMORY",
        "commit": committed,
        "clear": cleared,
        "records_committed": len(record_ids),
        **base,
    }


@dataclass
class ConsciousnessPulse:
    """Bounded heartbeat planner for the CPU consciousness slice."""

    reflection_frequency: int = 5
    heartbeat_count: int = 0

    def tick(
        self,
        *,
        prompt: str = "",
        stm: ShortTermMemory | None = None,
        mirror: ReflectionGraph | None = None,
        experience: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.heartbeat_count += 1
        frequency = max(1, int(self.reflection_frequency))
        reflection_due = self.heartbeat_count % frequency == 0
        reflection = None
        if reflection_due and mirror is not None:
            reflection = mirror.reflect(experience)
        return {
            "ok": True,
            "heartbeat_count": self.heartbeat_count,
            "reflection_due": reflection_due,
            "reflection": reflection,
            "fragment": select_soul_fragment(prompt),
            "consolidation_due": bool(stm and stm.consolidation_due),
            "consolidation_policy": "prepare_then_explicit_commit",
            "autonomous_thought": "DISABLED_CPU_ONLY",
            "writes_performed": False,
            "llm_authority": False,
            "authority": "cpu_deterministic_consciousness_pulse",
        }


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
        "implemented": [
            "soul_fragment_selector",
            "bounded_stm",
            "explicit_ltm_commit",
            "identity_drift_measurement",
            "deterministic_reflection_graph",
            "bounded_consciousness_pulse",
            "explicit_memory_commit_gate",
        ],
        "not_implemented": [
            "historical biological heartbeat loops",
            "LLM semantic authority",
            "automatic durable commit",
            "unbounded_semantic_memory_compression",
        ],
    }
