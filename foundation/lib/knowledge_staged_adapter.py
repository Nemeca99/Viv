"""Read-only semantic retrieval over an explicitly staged vector artifact.

This is an evidence path, not persistent-index admission. Every candidate is
re-checked against its source file hash before it can become a CPU fact.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from lib.knowledge_semantic_backend import _local_embedding, cosine_similarity
from lib.knowledge_source_contract import packet_from_retrieval

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "auto" / "knowledge"
WIKIPEDIA_ROOT = Path(r"F:\AI_Datasets\wikipedia_deduplicated")
ARTIFACT_GLOBS = (
    "wikipedia_semantic_shard_clean_v1_*.json",
    "wikipedia_semantic_shard_v1_*.json",
    "wikipedia_redirect_resolved_staged_vectors_v1_*.json",
)
STAGED_QUERY_THRESHOLD = 0.35
_RANK_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "how",
    "in", "is", "of", "on", "or", "the", "to", "under", "what", "whose",
    "with",
}


def _title_overlap(query_text: str, path_text: str) -> int:
    query_tokens = {
        token for token in re.findall(r"[a-z0-9]{3,}", str(query_text).casefold())
        if token not in _RANK_STOPWORDS
    }
    title = re.sub(r"^\d+_", "", Path(path_text).stem).casefold()
    title_tokens = set(re.findall(r"[a-z0-9]{3,}", title))
    return len(query_tokens.intersection(title_tokens))


def _source_overlap(query_text: str, source_text: str) -> int:
    """Count query content terms present in the verified source preview."""
    query_tokens = {
        token for token in re.findall(r"[a-z0-9]{3,}", str(query_text).casefold())
        if token not in _RANK_STOPWORDS
    }
    source_tokens = set(re.findall(r"[a-z0-9]{3,}", str(source_text).casefold()))
    return len(query_tokens.intersection(source_tokens))


def _latest_artifact() -> Path | None:
    candidates = sorted(
        {path for pattern in ARTIFACT_GLOBS for path in KNOWLEDGE_DIR.glob(pattern)},
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_text(row: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, str | None]:
    raw_path = Path(str(row.get("path") or ""))
    try:
        path = raw_path.resolve()
        path.relative_to(WIKIPEDIA_ROOT.resolve())
    except (OSError, ValueError):
        return None, None, "source_outside_wikipedia_root"
    if not path.is_file():
        return None, None, "source_missing"
    expected = str(row.get("source_sha256") or "").lower()
    if not expected or _sha256(path) != expected:
        return None, None, "source_hash_mismatch"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None, "source_read_failed"
    chunk_chars = max(256, min(int(row.get("chunk_chars") or 2048), 12000))
    ref = {
        "source_id": f"sha256:{expected}",
        "source_token": f"SRC_F_AI_DATASETS_{path.name}",
        "root": "F_AI_DATASETS",
        "kind": "wikipedia_staged_semantic",
        "bytes": path.stat().st_size,
        "sha256": expected,
        "readable": True,
    }
    return text[:chunk_chars].strip(), ref, None


def query(
    text: str,
    *,
    artifact_path: str | Path | None = None,
    k: int = 5,
    threshold: float = STAGED_QUERY_THRESHOLD,
) -> dict[str, Any]:
    """Query staged vectors without writing an index or source cache."""
    artifact = Path(artifact_path) if artifact_path else _latest_artifact()
    if artifact is None or not artifact.is_file():
        return {"ok": False, "state": "INCONCLUSIVE", "error": "staged_artifact_missing", "hits": [], "silence": True}
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "state": "INCONCLUSIVE", "error": f"artifact_read:{type(exc).__name__}", "hits": [], "silence": True}
    authority = payload.get("authority") or {}
    vector_index_written = authority.get("vector_index_written", payload.get("vector_index_written", False))
    training_authorized = authority.get("training_authorized", payload.get("training_authorized", False))
    if payload.get("state") != "VERIFIED" or vector_index_written or training_authorized:
        return {"ok": False, "state": "INCONCLUSIVE", "error": "staged_artifact_not_read_only", "hits": [], "silence": True}
    query_text = str(text or "").strip()
    if not query_text:
        return {"ok": False, "state": "INSUFFICIENT", "error": "empty_query", "hits": [], "silence": True}
    try:
        query_vector = _local_embedding(query_text)
    except Exception as exc:  # noqa: BLE001 — semantic retrieval fails closed
        return {"ok": False, "state": "INCONCLUSIVE", "error": f"embedding:{type(exc).__name__}", "hits": [], "silence": True}
    scored: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        vector = row.get("embedding") or []
        if len(vector) != len(query_vector) or not all(math.isfinite(float(value)) for value in vector):
            rejected["vector_invalid"] = rejected.get("vector_invalid", 0) + 1
            continue
        source_text, source_ref, error = _source_text(row)
        if error:
            rejected[error] = rejected.get(error, 0) + 1
            continue
        score = cosine_similarity(query_vector, [float(value) for value in vector])
        source_overlap = _source_overlap(query_text, source_text or "")
        query_term_count = max(
            1,
            len({
                token for token in re.findall(r"[a-z0-9]{3,}", query_text.casefold())
                if token not in _RANK_STOPWORDS
            }),
        )
        lexical_score = source_overlap / query_term_count
        lexical_gate = (
            score >= max(0.25, float(threshold) - 0.10)
            and source_overlap >= 2
            and lexical_score >= 0.25
        )
        if score < float(threshold) and not lexical_gate:
            continue
        title_overlap = _title_overlap(query_text, str(row.get("path") or ""))
        ranking_score = round(
            score
            + (0.15 * min(title_overlap, 3))
            + (0.25 * min(lexical_score, 0.75)),
            4,
        )
        scored.append({
            "claim": f"wikipedia_staged:{Path(str(row.get('path') or '')).stem.casefold()}",
            "text": source_text,
            "score": score,
            "ranking_score": ranking_score,
            "title_overlap": title_overlap,
            "source_overlap": source_overlap,
            "lexical_score": round(lexical_score, 4),
            "retrieval_similarity": score,
            "source_ref": source_ref,
            "source": "wikipedia_staged_semantic",
            "doc": Path(str(row.get("path") or "unknown")).name,
            "redirect_aliases": list(row.get("redirect_aliases") or []),
        })
    scored.sort(key=lambda hit: (-float(hit.get("ranking_score", hit["score"])), -float(hit["score"]), str(hit.get("doc"))))
    hits = scored[: max(1, min(int(k), 20))]
    return {
        "ok": True,
        "state": "VERIFIED" if hits else "INSUFFICIENT",
        "hits": hits,
        "silence": not hits,
        "mode": "staged_semantic_read_only",
        "artifact": str(artifact).replace("\\", "/"),
        "evidence": {
            "artifact_state": payload.get("state"),
            "vector_index_written": bool(vector_index_written),
            "persistent_index_written": bool(authority.get("persistent_index_written", payload.get("persistent_index_written", False))),
            "candidate_rows": len(payload.get("rows") or []),
            "verified_source_hits": len(scored),
            "rejected": rejected,
            "threshold": float(threshold),
            "model_sha256": payload.get("model_sha256"),
        },
    }


def query_packet(text: str, *, artifact_path: str | Path | None = None, k: int = 5, threshold: float = STAGED_QUERY_THRESHOLD) -> dict[str, Any]:
    result = query(text, artifact_path=artifact_path, k=k, threshold=threshold)
    return {**result, "packet": packet_from_retrieval(text, result.get("hits") or [])}
