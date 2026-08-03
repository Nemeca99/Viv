"""Deterministic, explicitly provisional cross-source claim alignment."""
from __future__ import annotations

import re
from typing import Any, Iterable

EVIDENCE_ROOTS = ("F_AI_DATASETS", "WIKIPEDIA_REST")
DEFAULT_MIN_OVERLAP = 0.05
_STOP = {
    "about", "after", "also", "been", "being", "from", "have", "into", "more",
    "over", "such", "that", "their", "there", "these", "they", "this", "through",
    "under", "were", "which", "with", "would", "your",
}


def normalize_claim_key(text: str) -> str:
    words = [word for word in re.findall(r"[a-z0-9]{3,}", (text or "").casefold()) if word not in _STOP]
    return "_".join(words[:12]) or "unknown"


def _tokens(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]{4,}", (text or "").casefold())
        if word not in _STOP
    }


def _jaccard(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return round(len(a & b) / max(1, len(a | b)), 4) if a and b else 0.0


def _semantic_compare(left: str, right: str) -> tuple[float, str]:
    """Prefer local embeddings, then preserve the existing provisional bridge."""
    try:
        from lib.knowledge_semantic_backend import semantic_compare

        result = semantic_compare(left, right)
        if result.get("ok"):
            return float(result["score"]), "ollama_viv_embed"
    except Exception:  # noqa: BLE001 — semantic backend remains optional and fail-closed
        pass
    try:
        from lib.viv_shadow_judge import semantic_compare

        return float(semantic_compare(left, right)), "lib.viv_shadow_judge.semantic_compare"
    except Exception:  # noqa: BLE001 — alignment remains deterministic if optional import fails
        return _jaccard(left, right), "knowledge_claim_alignment.local_token_fallback"


def align_claims(
    query: str,
    facts: Iterable[dict[str, Any]],
    *,
    evidence_roots: tuple[str, ...] = EVIDENCE_ROOTS,
    min_overlap: float = DEFAULT_MIN_OVERLAP,
) -> dict[str, Any]:
    """Compare evidence sources; below threshold is INCONCLUSIVE, never pass."""
    grouped: dict[str, list[str]] = {}
    for row in facts:
        source = dict(row.get("source") or {})
        root = str(source.get("root") or "")
        if root in evidence_roots:
            grouped.setdefault(root, []).append(str(row.get("value") or ""))
    present = sorted(grouped)
    missing = [root for root in evidence_roots if root not in grouped]
    pairwise: dict[str, float] = {}
    judge_interfaces: set[str] = set()
    if not missing:
        for index, left_root in enumerate(evidence_roots):
            for right_root in evidence_roots[index + 1 :]:
                left = " ".join(grouped[left_root])
                right = " ".join(grouped[right_root])
                score, judge = _semantic_compare(left, right)
                judge_interfaces.add(judge)
                pairwise[f"{left_root}~{right_root}"] = score
    min_score = min(pairwise.values()) if pairwise else 0.0
    state = "INCONCLUSIVE"
    if not present:
        state = "INSUFFICIENT"
    elif not missing and min_score >= float(min_overlap):
        state = "CORROBORATED_PROVISIONAL"
    return {
        "version": "knowledge_claim_alignment_v1",
        "query_key": normalize_claim_key(query),
        "state": state,
        "evidence_roots": list(evidence_roots),
        "present_roots": present,
        "missing_roots": missing,
        "pairwise_overlap": pairwise,
        "min_overlap": min_score,
        "required_overlap": float(min_overlap),
        "authority": "cpu_deterministic_proxy",
        "judge_interfaces": sorted(judge_interfaces) or ["not_run"],
        "warning": "Provisional lexical alignment is not semantic entailment; below-threshold cases remain INCONCLUSIVE.",
    }
