"""Bounded CPU retrieval ranking; TF-IDF is ranking evidence, not entailment."""
from __future__ import annotations

from typing import Any, Iterable


def rank_candidates(query: str, candidates: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Rank already-filtered candidates with optional local TF-IDF.

    The function never creates evidence or changes provenance. If scikit-learn
    is unavailable or the input is too small/invalid, it returns deterministic
    keyword ordering and an explicit fallback mode.
    """
    rows = [dict(row) for row in candidates]
    if len(rows) < 2:
        return rows, "keyword_cpu"
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        texts = [str(query or "")] + [str(row.get("text") or "") for row in rows]
        vectorizer = TfidfVectorizer(lowercase=True, token_pattern=r"(?u)\b[a-zA-Z0-9_]{3,}\b")
        matrix = vectorizer.fit_transform(texts)
        similarities = cosine_similarity(matrix[0:1], matrix[1:]).ravel().tolist()
        for row, similarity in zip(rows, similarities):
            row["retrieval_similarity"] = round(float(similarity), 4)
            row["retrieval_rank_score"] = round(float(similarity) + min(int(row.get("score") or 0), 10) * 0.01, 4)
        rows.sort(
            key=lambda row: (
                -float(row.get("retrieval_rank_score") or 0.0),
                -int(row.get("score") or 0),
                str(row.get("source") or ""),
                int(row.get("i") or 0),
            )
        )
        return rows, "tfidf_cpu_provisional"
    except Exception:  # noqa: BLE001 — deterministic fallback is explicit
        rows.sort(key=lambda row: (-int(row.get("score") or 0), str(row.get("source") or ""), int(row.get("i") or 0)))
        return rows, "keyword_cpu"
