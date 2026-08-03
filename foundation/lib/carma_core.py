"""Deterministic CARMA memory planning primitives.

CARMA decides what can be indexed and how records relate.  It does not invent
facts and it does not bypass ``memory_core``'s write gate.  Embedding-backed
semantic search remains an optional, separately verified sensor.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable


MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.2 carma_core"
_TOKEN = re.compile(r"[a-z0-9_]{3,}")
_STOP = {"the", "and", "for", "with", "from", "that", "this", "have", "are", "was", "what", "how"}


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
        "semantic_authority": False,
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
    concepts = sorted({concept for row in rows for concept in row.get("concepts") or []})
    return {
        "ok": bool(rows),
        "fragment_count": len(rows),
        "fragment_ids": [row.get("id") for row in rows],
        "concepts": concepts,
        "links": link_fragments(rows),
        "semantic_compression": "not_performed",
        "requires": "verified_carma_compressor_before_durable_commit",
        "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
    }

