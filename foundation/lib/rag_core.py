"""CPU-owned, provenance-preserving retrieval facade for Viv.

The legacy RAG sources provide several useful retrieval mechanisms, but the
active foundation previously exposed them through separate adapters.  This
module is the narrow V1 CPU boundary that joins those mechanisms without
copying the legacy mutable index or granting a renderer authority.

The facade is deliberately read-only:

* ``manual`` uses the hash-verified Alpha ManualOracle.
* ``adapter`` uses the existing bounded keyword adapter index.
* ``staged_semantic`` uses the explicitly staged, source-revalidated vector
  artifact.
* ``wikipedia_local`` uses the read-only indexed article path.
* ``auto`` preserves the existing adapter-then-local fallback behavior.

Every admitted hit must carry a source hash.  Returned citations contain a
logical source token rather than a physical path, and the result always states
that no persistent index, training, or renderer authority was used.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lib.aios_adapter_knowledge import (
    query_manual_packet as _query_manual_packet,
    query_packet as _query_adapter_packet,
)
from lib.knowledge_external_adapters import query_legacy_wikipedia
from lib.knowledge_source_contract import packet_from_retrieval
from lib.knowledge_staged_adapter import query_packet as _query_staged_packet


_MODES = {"auto", "manual", "adapter", "staged_semantic", "wikipedia_local"}


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _source_token(source_ref: dict[str, Any], hit: dict[str, Any]) -> str:
    existing = str(source_ref.get("source_token") or "").strip()
    if existing:
        return existing
    root = re.sub(r"[^A-Za-z0-9]+", "_", str(source_ref.get("root") or "knowledge")).strip("_") or "KNOWLEDGE"
    raw_path = str(source_ref.get("path") or hit.get("doc") or "unknown")
    name = re.sub(r"[^A-Za-z0-9]+", "_", Path(raw_path).name).strip("_") or "unknown"
    return f"SRC_{root.upper()}_{name}"


def _source_hash(source_ref: dict[str, Any]) -> str:
    # Manual sections carry both the file hash and a section hash.  The file
    # hash is the authoritative provenance binding for a retrieval citation.
    return str(source_ref.get("source_sha256") or source_ref.get("sha256") or "").strip().lower()


def _safe_source_ref(source_ref: dict[str, Any], hit: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    digest = _source_hash(source_ref)
    if not digest:
        return {}, {"reason": "missing_source_hash", "source": str(hit.get("source") or "unknown")}
    if not bool(source_ref.get("readable", True)):
        return {}, {"reason": "source_not_readable", "source": str(hit.get("source") or "unknown")}
    safe: dict[str, Any] = {
        "source_id": str(source_ref.get("source_id") or f"sha256:{digest}"),
        "source_token": _source_token(source_ref, hit),
        "root": str(source_ref.get("root") or "knowledge_index"),
        "kind": str(source_ref.get("kind") or "retrieved_text"),
        "bytes": int(source_ref.get("bytes") or len(str(hit.get("text") or "").encode("utf-8"))),
        "sha256": digest,
        "readable": True,
    }
    modified = source_ref.get("modified_utc")
    if modified is not None:
        safe["modified_utc"] = modified
    if source_ref.get("source_sha256"):
        safe["source_sha256"] = digest
    if source_ref.get("sha256") and source_ref.get("source_sha256"):
        safe["section_sha256"] = str(source_ref.get("sha256")).lower()
    for field in ("start_line", "end_line"):
        if source_ref.get(field) is not None:
            safe[field] = int(source_ref[field])
    return safe, None


def _admit_hits(hits: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    admitted: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, raw in enumerate(hits):
        if not isinstance(raw, dict):
            rejected.append({"index": index, "reason": "hit_not_object"})
            continue
        text = str(raw.get("text") or raw.get("value") or "").strip()
        if not text:
            rejected.append({"index": index, "reason": "empty_hit_text"})
            continue
        raw_ref = raw.get("source_ref") or raw.get("source") or {}
        source_ref = dict(raw_ref) if isinstance(raw_ref, dict) else {}
        safe_ref, error = _safe_source_ref(source_ref, raw)
        if error:
            error["index"] = index
            rejected.append(error)
            continue
        hit = dict(raw)
        hit["text"] = text
        hit["source_ref"] = safe_ref
        hit.pop("path", None)
        admitted.append(hit)
        citations.append(
            {
                "claim": str(hit.get("claim") or f"retrieved_evidence_{index}"),
                "source_id": safe_ref["source_id"],
                "source_token": safe_ref["source_token"],
                "root": safe_ref["root"],
                "kind": safe_ref["kind"],
                "source_sha256": safe_ref["sha256"],
            }
        )
    return admitted, citations, rejected


def _legacy_result(query: str, *, top_k: int, resolve_redirects: bool) -> dict[str, Any]:
    result = query_legacy_wikipedia(
        query,
        limit=top_k,
        max_chars=12000,
        resolve_redirects=resolve_redirects,
    )
    hits = []
    for fact in result.get("facts") or []:
        hits.append(
            {
                "source": "wikipedia_local",
                "doc": (fact.get("source") or {}).get("path"),
                "score": 1,
                "text": fact.get("value"),
                "claim": fact.get("claim"),
                "source_ref": fact.get("source"),
            }
        )
    return {
        **result,
        "hits": hits,
        "packet": packet_from_retrieval(query, hits),
        # Preserve the stable CPU-pipeline mode while retaining the detailed
        # legacy resolver mode for evidence.
        "legacy_mode": result.get("mode"),
        "mode": "wikipedia_local_read_only",
    }


def _decorate(
    result: dict[str, Any],
    *,
    query: str,
    route: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_hits = result.get("hits") or []
    admitted, citations, rejected = _admit_hits(raw_hits)
    packet = packet_from_retrieval(query, admitted)
    packet_state = str((result.get("packet") or {}).get("state") or "")
    underlying_state = str(result.get("state") or "")

    if underlying_state == "INCONCLUSIVE":
        state = "INCONCLUSIVE"
    elif packet_state == "CONFLICT":
        state = "CONFLICT"
    elif rejected and not admitted:
        state = "INCONCLUSIVE"
    elif admitted:
        state = packet_state if packet_state in {"PARTIAL", "VERIFIED"} else "VERIFIED"
    else:
        state = "ABSTAIN"

    decorated = dict(result)
    decorated.update(
        {
            "ok": state not in {"INCONCLUSIVE", "DENIED"} and not bool(result.get("error")),
            "state": state,
            "hits": admitted,
            "packet": packet,
            "citations": citations,
            "rag_core": {
                "version": "rag_core_v1",
                "route": route,
                "attempts": attempts,
                "candidate_hit_count": len(raw_hits),
                "admitted_hit_count": len(admitted),
                "rejected_hit_count": len(rejected),
                "rejected": rejected,
                "source_hashes_present": all(bool(row.get("source_sha256")) for row in citations),
                "persistent_index_written": False,
                "writes_performed": False,
                "training_authorized": False,
                "llm_authority": False,
                "at": _utc(),
            },
            "writes_performed": False,
            "persistent_index_written": False,
            "training_authorized": False,
            "llm_authority": False,
        }
    )
    return decorated


class RAGCore:
    """Stateless CPU retrieval boundary with explicit source adjudication."""

    @staticmethod
    def validate_hits(hits: Iterable[dict[str, Any]]) -> dict[str, Any]:
        admitted, citations, rejected = _admit_hits(hits)
        return {
            "ok": bool(admitted) and not rejected,
            "admitted": admitted,
            "citations": citations,
            "rejected": rejected,
            "writes_performed": False,
            "llm_authority": False,
        }

    def retrieve(
        self,
        text: str,
        *,
        mode: str = "auto",
        top_k: int = 5,
        source_roots: tuple[str, ...] | None = None,
        local_wikipedia: bool = True,
        staged_artifact: str | Path | None = None,
        staged_threshold: float = 0.35,
        resolve_redirects: bool = True,
    ) -> dict[str, Any]:
        query = str(text or "").strip()
        selected_mode = str(mode or "auto").strip().casefold()
        if selected_mode not in _MODES:
            return _decorate(
                {"ok": False, "state": "INCONCLUSIVE", "error": f"unsupported_mode:{selected_mode}", "hits": []},
                query=query,
                route=selected_mode,
                attempts=[],
            )
        if not query:
            return _decorate(
                {"ok": False, "state": "ABSTAIN", "error": "empty_query", "hits": []},
                query=query,
                route=selected_mode,
                attempts=[],
            )

        attempts: list[dict[str, Any]] = []

        def run(route: str) -> dict[str, Any]:
            if route == "manual":
                return _query_manual_packet(query, k=top_k)
            if route == "adapter":
                return _query_adapter_packet(query, k=top_k, source_roots=source_roots)
            if route == "staged_semantic":
                return _query_staged_packet(query, artifact_path=staged_artifact, k=top_k, threshold=staged_threshold)
            if route == "wikipedia_local":
                return _legacy_result(query, top_k=top_k, resolve_redirects=resolve_redirects)
            raise ValueError(f"unknown_route:{route}")

        if selected_mode == "auto":
            first = run("adapter")
            attempts.append({"route": "adapter", "state": first.get("state"), "hits": len(first.get("hits") or [])})
            if first.get("hits") or not local_wikipedia or first.get("state") == "INCONCLUSIVE":
                return _decorate(first, query=query, route="adapter", attempts=attempts)
            second = run("wikipedia_local")
            attempts.append({"route": "wikipedia_local", "state": second.get("state"), "hits": len(second.get("hits") or [])})
            return _decorate(second, query=query, route="wikipedia_local", attempts=attempts)

        result = run(selected_mode)
        attempts.append({"route": selected_mode, "state": result.get("state"), "hits": len(result.get("hits") or [])})
        return _decorate(result, query=query, route=selected_mode, attempts=attempts)


_DEFAULT = RAGCore()


def retrieve(text: str, **kwargs: Any) -> dict[str, Any]:
    """Functional entry point for the CPU reasoning pipeline."""
    return _DEFAULT.retrieve(text, **kwargs)


__all__ = ["RAGCore", "retrieve"]
