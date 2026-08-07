"""Deterministic CARMA memory planning primitives.

CARMA decides what can be indexed and how records relate.  It does not invent
facts and it does not bypass ``memory_core``'s write gate.  Embedding-backed
semantic search remains an optional, separately verified sensor.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Iterable, Mapping


MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.2 carma_core"
_TOKEN = re.compile(r"[a-z0-9_]{3,}")
_STOP = {"the", "and", "for", "with", "from", "that", "this", "have", "are", "was", "what", "how"}
STM_CAPACITY = 100
STM_CONSOLIDATION_THRESHOLD = 0.80
MAX_RETRIEVAL = 20


def extract_concepts(text: str, *, limit: int = 12) -> list[str]:
    """Stable lexical concepts; this is not a semantic truth claim."""
    counts: dict[str, int] = {}
    for token in _TOKEN.findall(str(text).casefold()):
        if token in _STOP:
            continue
        counts[token] = counts.get(token, 0) + 1
    return [token for token, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[: max(0, int(limit))]]


def make_fragment(text: str, *, provenance: str = "live", source: str = "user_input") -> dict[str, Any]:
    clean = str(text).strip()
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()
    return {
        "id": f"carma-{digest[:16]}",
        "content": clean,
        "concepts": extract_concepts(clean),
        "provenance": str(provenance),
        "source": str(source),
        "sha256": digest,
        "record_version": "carma_fragment_v1",
        "semantic_authority": False,
    }


def validate_fragment(fragment: Mapping[str, Any]) -> dict[str, Any]:
    """Validate identity, content hash, provenance, and derived concepts."""
    if not isinstance(fragment, Mapping):
        return {"ok": False, "state": "ABSTAIN", "reason": "fragment_not_mapping"}
    content = str(fragment.get("content") or "").strip()
    if not content:
        return {"ok": False, "state": "ABSTAIN", "reason": "empty_fragment"}
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    expected_id = f"carma-{digest[:16]}"
    supplied_hash = str(fragment.get("sha256") or "").strip().casefold()
    supplied_id = str(fragment.get("id") or "").strip()
    provenance = str(fragment.get("provenance") or "").strip().casefold()
    if supplied_hash != digest:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "fragment_hash_mismatch",
            "expected_sha256": digest,
            "supplied_sha256": supplied_hash or None,
        }
    if supplied_id != expected_id:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "fragment_id_mismatch",
            "expected_id": expected_id,
            "supplied_id": supplied_id or None,
        }
    if not provenance:
        return {"ok": False, "state": "ABSTAIN", "reason": "missing_provenance", "fragment_id": supplied_id}
    derived = extract_concepts(content)
    supplied_concepts = fragment.get("concepts")
    if supplied_concepts is not None:
        if not isinstance(supplied_concepts, (list, tuple)):
            return {"ok": False, "state": "ABSTAIN", "reason": "concepts_not_sequence", "fragment_id": supplied_id}
        if set(str(value) for value in supplied_concepts) != set(derived):
            return {"ok": False, "state": "ABSTAIN", "reason": "derived_concepts_mismatch", "fragment_id": supplied_id}
        concepts_source = "record"
    else:
        concepts_source = "deterministic_extraction"
    return {
        "ok": True,
        "state": "VERIFIED",
        "fragment_id": supplied_id,
        "sha256": digest,
        "provenance": provenance,
        "source": str(fragment.get("source") or "unknown"),
        "content": content,
        "concepts": derived,
        "concepts_source": concepts_source,
        "semantic_authority": False,
        "llm_authority": False,
    }


def link_fragments(fragments: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [row for row in fragments if isinstance(row, dict)]
    links: list[dict[str, Any]] = []
    for index, left in enumerate(rows):
        left_concepts = set(left.get("concepts") or [])
        for right in rows[index + 1 :]:
            shared = sorted(left_concepts.intersection(right.get("concepts") or []))
            if shared:
                links.append({"left": left.get("id"), "right": right.get("id"), "shared_concepts": shared, "authority": "deterministic_overlap"})
    return links


def consolidation_package(fragments: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in fragments if isinstance(row, dict)]
    validations = [validate_fragment(row) for row in rows]
    valid_rows = [row for row, validation in zip(rows, validations) if validation.get("ok")]
    invalid = [validation for validation in validations if not validation.get("ok")]
    concepts = sorted({concept for row in valid_rows for concept in row.get("concepts") or []})
    stm_plan = plan_stm_ltm(valid_rows)
    return {
        "ok": bool(rows),
        "fragment_count": len(rows),
        "valid_fragment_count": len(valid_rows),
        "invalid_fragment_count": len(invalid),
        "invalid_fragments": invalid,
        "fragment_ids": [row.get("id") for row in valid_rows],
        "concepts": concepts,
        "links": link_fragments(valid_rows),
        "semantic_compression": "not_performed",
        "requires": "verified_carma_compressor_before_durable_commit",
        "stm_plan": stm_plan,
        "writes_performed": False,
        "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
    }


def retrieval_packet(query: str, fragments: Iterable[Mapping[str, Any]], *, top: int = 5) -> dict[str, Any]:
    """Return a provenance-bearing lexical retrieval packet without claiming semantics."""
    clean_query = str(query or "").strip()
    query_concepts = set(extract_concepts(clean_query))
    limit = max(1, min(int(top), MAX_RETRIEVAL))
    if not clean_query or not query_concepts:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "empty_or_unindexable_query",
            "query": clean_query,
            "hits": [],
            "retrieval_mode": "lexical_overlap",
            "semantic_authority": False,
            "writes_performed": False,
            "llm_authority": False,
        }
    candidates: list[dict[str, Any]] = []
    rejected = 0
    for raw in fragments:
        validation = validate_fragment(raw)
        if not validation.get("ok"):
            rejected += 1
            continue
        concepts = set(validation["concepts"])
        union = query_concepts | concepts
        score = len(query_concepts & concepts) / len(union) if union else 0.0
        if score <= 0.0:
            continue
        candidates.append(
            {
                "id": validation["fragment_id"],
                "content": validation["content"],
                "provenance": validation["provenance"],
                "source": validation["source"],
                "sha256": validation["sha256"],
                "concepts": validation["concepts"],
                "lexical_jaccard": round(score, 6),
                "support_type": "source_fragment",
            }
        )
    candidates.sort(key=lambda row: (-float(row["lexical_jaccard"]), str(row["id"])))
    hits = candidates[:limit]
    return {
        "ok": bool(hits),
        "state": "VERIFIED" if hits else "ABSTAIN",
        "reason": "lexical_hits" if hits else "no_lexical_hits",
        "query": clean_query,
        "query_concepts": sorted(query_concepts),
        "hits": hits,
        "rejected_fragments": rejected,
        "retrieval_mode": "lexical_overlap",
        "semantic_authority": False,
        "writes_performed": False,
        "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
    }


def plan_stm_ltm(
    fragments: Iterable[Mapping[str, Any]],
    *,
    capacity: int = STM_CAPACITY,
    consolidation_threshold: float = STM_CONSOLIDATION_THRESHOLD,
    explicit_commit: bool = False,
) -> dict[str, Any]:
    """Plan STM→LTM handling without performing a durable commit."""
    rows = list(fragments)
    valid = [row for row in rows if validate_fragment(row).get("ok")]
    bounded_capacity = max(1, int(capacity))
    threshold = max(0.0, min(float(consolidation_threshold), 1.0))
    due_at = max(1, int(math.ceil(bounded_capacity * threshold)))
    base = {
        "fragment_count": len(valid),
        "capacity": bounded_capacity,
        "threshold": threshold,
        "due_at": due_at,
        "explicit_commit": bool(explicit_commit),
        "writes_performed": False,
        "durable_commit_performed": False,
        "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
    }
    if len(valid) < due_at:
        return {"ok": True, "state": "NOT_DUE", "reason": "stm_below_consolidation_threshold", **base}
    if not explicit_commit:
        return {"ok": True, "state": "HOLD", "reason": "explicit_ltm_commit_required", **base}
    return {"ok": True, "state": "READY_FOR_GOVERNED_EXECUTOR", "reason": "commit_authorized_for_handoff", **base}


def module_status() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "carma_core",
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
        "implemented": [
            "provenance_and_content_hash_validation",
            "deterministic_lexical_retrieval_packet",
            "stm_ltm_threshold_planning",
            "overlap_link_planning",
            "explicit_no_semantic_compression_boundary",
        ],
        "not_implemented": [
            "durable_ltm_commit",
            "unverified_semantic_summary_generation",
            "automatic_memory_deletion",
            "llm_memory_authority",
        ],
        "writes_performed": False,
        "durable_commit_performed": False,
        "llm_authority": False,
    }
