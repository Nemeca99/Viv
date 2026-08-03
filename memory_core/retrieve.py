"""Deterministic CARMA retrieval with bounded CPU re-ranking.

Keyword matching remains the admission filter. Re-ranking is a provisional
lexical similarity signal only; it does not create facts or assert entailment.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from memory_core.paths import CARMA_ROOT, INDEX_PATH, PROVENANCE_DIRS


def _tokenize(query: str) -> list[str]:
    return [t for t in re.split(r"[^\w]+", query.lower()) if len(t) >= 2]


def _score_line(line: str, tokens: list[str], tag_filter: set[str]) -> float:
    low = line.lower()
    if tag_filter:
        if not any(f"[{t}]" in low for t in tag_filter):
            return 0.0
    if not tokens:
        return 0.1
    hits = sum(1 for t in tokens if t in low)
    return hits / len(tokens)


def _iter_txt_files() -> list[Path]:
    out: list[Path] = []
    for prov_dir in PROVENANCE_DIRS.values():
        if prov_dir.is_dir():
            out.extend(sorted(prov_dir.glob("*.txt")))
    return out


def _rank_keyword_hits(query: str, hits: list[tuple[float, str, str, int]]) -> tuple[list[tuple[float, str, str, int, float, float]], str]:
    """Re-rank matched lines with deterministic CPU cosine similarity."""
    if len(hits) < 2:
        return [(score, path, line, line_no, 0.0, score) for score, path, line, line_no in hits], "keyword_cpu"
    query_tokens = _tokenize(query)
    if not query_tokens:
        return [(score, path, line, line_no, 0.0, score) for score, path, line, line_no in hits], "keyword_cpu"
    vocabulary = set(query_tokens)
    rows: list[tuple[float, str, str, int, dict[str, int]]] = []
    for score, path, line, line_no in hits:
        tokens = _tokenize(line)
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
            vocabulary.add(token)
        rows.append((score, path, line, line_no, counts))
    query_counts = {token: query_tokens.count(token) for token in set(query_tokens)}
    query_norm = sum(value * value for value in query_counts.values()) ** 0.5
    if query_norm <= 0.0:
        return [(score, path, line, line_no, 0.0, score) for score, path, line, line_no, _ in rows], "keyword_cpu"
    ranked: list[tuple[float, str, str, int, float, float]] = []
    for score, path, line, line_no, counts in rows:
        dot = sum(query_counts.get(token, 0) * counts.get(token, 0) for token in vocabulary)
        row_norm = sum(value * value for value in counts.values()) ** 0.5
        similarity = dot / (query_norm * row_norm) if row_norm > 0.0 else 0.0
        combined = similarity + min(score, 1.0) * 0.01
        ranked.append((score, path, line, line_no, round(similarity, 4), round(combined, 4)))
    ranked.sort(key=lambda row: (-row[5], -row[0], row[1], row[3]))
    return ranked, "cpu_cosine_provisional"


def retrieve(
    query: str,
    *,
    top: int = 5,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    tokens = _tokenize(query)
    tag_filter = {t.strip().lower() for t in (tags or []) if t.strip()}
    hits: list[tuple[float, str, str, int]] = []

    for path in _iter_txt_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            score = _score_line(line, tokens, tag_filter)
            if score > 0:
                hits.append((score, str(path), line, i))

    ranked, retrieval_mode = _rank_keyword_hits(query, hits)
    results: list[dict[str, Any]] = []
    for score, path, line, line_no, similarity, rank_score in ranked[: max(1, top)]:
        results.append(
            {
                "score": round(score, 3),
                "retrieval_similarity": similarity,
                "retrieval_rank_score": rank_score,
                "retrieval_mode": retrieval_mode,
                "path": path.replace("\\", "/"),
                "line_no": line_no,
                "text": line[:500],
            }
        )
    return results


def index_summary() -> dict[str, Any]:
    if not INDEX_PATH.is_file():
        return {"entries": 0, "files": []}
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"entries": 0, "files": []}
    entries = data.get("entries") or []
    return {"entries": len(entries), "files": data.get("files") or [], "updated_at": data.get("updated_at")}


def carma_file_count() -> int:
    n = 0
    if CARMA_ROOT.is_dir():
        n = sum(1 for p in CARMA_ROOT.rglob("*.txt") if p.is_file())
    return n
