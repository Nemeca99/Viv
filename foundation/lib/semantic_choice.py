"""CPU policy for choosing among verified equivalent expressions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from lib.aios_personality import modulate_for_s_n, weights


@dataclass(frozen=True)
class ExpressionCandidate:
    text: str
    semantic_key: str
    processing_cost: float
    clarity: float = 1.0
    warmth: float = 0.5
    technicality: float = 0.5
    risk_penalty: float = 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def rank_equivalents(
    candidates: Iterable[ExpressionCandidate],
    *,
    s_n: float = 0.5,
    semantic_key: str | None = None,
) -> list[dict[str, Any]]:
    """Rank candidates only within one verified semantic equivalence class."""
    items = list(candidates)
    if not items:
        return []
    key = semantic_key or items[0].semantic_key
    if any(item.semantic_key != key for item in items):
        raise ValueError("semantic_choice requires one verified semantic_key")
    w = modulate_for_s_n(weights(), s_n)
    costs = [max(0.0, float(item.processing_cost)) for item in items]
    low_cost = min(costs)
    high_cost = max(costs)
    cost_span = high_cost - low_cost
    rows = []
    for item in items:
        risk = _clamp(item.risk_penalty)
        raw_cost = max(0.0, float(item.processing_cost))
        normalized_cost = (raw_cost - low_cost) / cost_span if cost_span > 0 else 0.0
        score = (
            1.25 * _clamp(item.clarity)
            + w.get("empathy", 0.8) * _clamp(item.warmth)
            + w.get("technical_depth", 0.75) * _clamp(item.technicality)
            + w.get("directness", 0.78) * (1.0 - risk)
            - w.get("authenticity", 0.95) * risk
            - 0.5 * normalized_cost
        )
        rows.append({
            "text": item.text,
            "semantic_key": key,
            "score": round(score, 8),
            "processing_cost": item.processing_cost,
            "normalized_processing_cost": round(normalized_cost, 8),
        })
    return sorted(rows, key=lambda row: (row["score"], -row["processing_cost"]), reverse=True)


def choose_equivalent(
    candidates: Iterable[ExpressionCandidate],
    *,
    s_n: float = 0.5,
    semantic_key: str | None = None,
) -> dict[str, Any]:
    ranked = rank_equivalents(candidates, s_n=s_n, semantic_key=semantic_key)
    if not ranked:
        return {"ok": False, "reason": "no_candidates"}
    return {"ok": True, "chosen": ranked[0], "ranked": ranked}
