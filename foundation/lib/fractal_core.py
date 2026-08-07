"""Bounded CPU policy and allocation helpers for ``fractal_core``.

This is a read-only foundation slice of the legacy fractal design.  It
classifies a query, proposes bounded policies, allocates a finite span budget,
and reports cache observations.  It never mutates cache or telemetry, invokes
an LLM, executes work, or writes durable state.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

MODULE_ID = "fractal_core"
VERSION = "v1"
MANUAL_SECTION = "3.11"
MAX_QUERY_CHARS = 2000
MAX_HEADS = 4
MAX_SPANS = 32
MAX_BUDGET = 10000
QUERY_TYPES = ("logic", "pattern_language", "refactoring", "meta")

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "logic": ("why", "because", "prove", "logic", "reason", "cause", "if", "then"),
    "pattern_language": ("pattern", "uml", "token", "grammar", "language", "structure", "syntax"),
    "refactoring": ("build", "change", "fix", "refactor", "implement", "code", "rewrite", "test"),
    "meta": ("explain", "compare", "status", "plan", "reflect", "summarize", "how", "what"),
}


def _flags() -> dict[str, bool]:
    return {
        "filesystem_read": False,
        "filesystem_write": False,
        "cache_mutation": False,
        "telemetry_learning": False,
        "execution": False,
        "llm_authority": False,
    }


def _clean_query(text: Any) -> str:
    return " ".join(str(text or "").split())[:MAX_QUERY_CHARS]


def _score(text: str, words: Sequence[str], *, question: bool = False) -> float:
    lowered = text.casefold()
    score = sum(1.0 for word in words if word in lowered)
    if question and "?" in text:
        score += 0.25
    return score


def classify_query(text: Any, history: Iterable[Any] = ()) -> dict[str, Any]:
    """Return a deterministic multi-head query mixture and dominant head."""
    clean = _clean_query(text)
    raw = {name: _score(clean, words, question=name == "meta") for name, words in _KEYWORDS.items()}
    if not clean:
        raw = {name: 0.0 for name in QUERY_TYPES}
    total = sum(raw.values())
    if total <= 0:
        raw["meta"] = 1.0
        total = 1.0
    mixture = {name: round(raw[name] / total, 6) for name in QUERY_TYPES}
    dominant = max(QUERY_TYPES, key=lambda name: (mixture[name], -QUERY_TYPES.index(name)))
    confidence = round(mixture[dominant], 6)
    history_count = min(len(tuple(history)), 8)
    return {
        "ok": bool(clean),
        "state": "VERIFIED" if clean else "INSUFFICIENT",
        "query": clean,
        "heads": list(QUERY_TYPES),
        "raw_scores": raw,
        "mixture": mixture,
        "dominant": dominant,
        "confidence": confidence,
        "history_count": history_count,
        "bounded": True,
        "authority": "cpu_deterministic_classification",
        "flags": _flags(),
    }


def emit_policies(mixture: Mapping[str, Any], *, global_budget: int = 3500) -> dict[str, Any]:
    """Create policy proposals without applying them to runtime state."""
    budget = max(1, min(int(global_budget), MAX_BUDGET))
    weights = {name: max(0.0, float(mixture.get(name, 0.0) or 0.0)) for name in QUERY_TYPES}
    total = sum(weights.values()) or 1.0
    weights = {name: value / total for name, value in weights.items()}
    return {
        "ok": True,
        "state": "PROPOSED",
        "global_budget": budget,
        "token_policy": {"budget": budget, "weight": round(weights["pattern_language"], 6)},
        "memory_policy": {"budget": max(64, budget // 8), "weight": round(weights["meta"], 6)},
        "code_policy": {"budget": max(64, budget // 4), "weight": round(weights["refactoring"], 6)},
        "arbiter_policy": {"budget": max(64, budget // 8), "weight": round(weights["logic"], 6)},
        "lessons_policy": {"enabled": False, "reason": "durable_learning_not_authorized"},
        "applied": False,
        "authority": "cpu_deterministic_policy_proposal",
        "flags": _flags(),
    }


def allocate_spans(
    spans: Sequence[Mapping[str, Any]],
    budget: int,
    *,
    mixture: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Select a deterministic value-maximizing subset under a cost budget."""
    limit = max(0, min(int(budget), MAX_BUDGET))
    rows = list(spans)[:MAX_SPANS]
    values: list[tuple[str, int, int, str]] = []
    for index, item in enumerate(rows):
        try:
            name = str(item.get("id") or item.get("name") or f"span_{index}")
            cost = max(0, int(item.get("cost", 0)))
            value = max(0, int(item.get("value", 0)))
        except (TypeError, ValueError):
            continue
        if cost <= limit:
            values.append((name, cost, value, str(item.get("kind") or "generic")))
    dp: list[tuple[int, tuple[str, ...]]] = [(0, ()) for _ in range(limit + 1)]
    for name, cost, value, _kind in values:
        for capacity in range(limit, cost - 1, -1):
            previous_value, previous_ids = dp[capacity - cost]
            candidate = (previous_value + value, previous_ids + (name,))
            current = dp[capacity]
            if candidate[0] > current[0] or (candidate[0] == current[0] and candidate[1] < current[1]):
                dp[capacity] = candidate
    best_value, selected = max(dp, key=lambda row: (row[0], -sum(next((c for n, c, _v, _k in values if n == sid), 0) for sid in row[1])))
    selected_set = set(selected)
    selected_cost = sum(cost for name, cost, _value, _kind in values if name in selected_set)
    return {
        "ok": True,
        "state": "VERIFIED",
        "budget": limit,
        "selected": list(selected),
        "selected_cost": selected_cost,
        "value": best_value,
        "rejected": [name for name, _cost, _value, _kind in values if name not in selected_set],
        "mixture": dict(mixture or {}),
        "bounded": True,
        "authority": "cpu_deterministic_knapsack",
        "flags": _flags(),
    }


def propose_threshold(observations: Iterable[Mapping[str, Any]], *, current: float = 0.75, target: float = 0.80) -> dict[str, Any]:
    """Report a bounded threshold proposal; never applies configuration."""
    scores: list[float] = []
    for row in list(observations)[:128]:
        try:
            value = float(row.get("success", row.get("score")))
        except (TypeError, ValueError):
            continue
        if 0.0 <= value <= 1.0:
            scores.append(value)
    mean = sum(scores) / len(scores) if scores else None
    proposed = max(0.0, min(1.0, float(target if mean is None else (float(current) + (float(target) - mean) * 0.25))))
    return {
        "ok": True,
        "state": "PROPOSED",
        "observations": len(scores),
        "mean_success": None if mean is None else round(mean, 6),
        "current": max(0.0, min(1.0, float(current))),
        "target": max(0.0, min(1.0, float(target))),
        "proposed": round(proposed, 6),
        "applied": False,
        "authority": "cpu_deterministic_threshold_proposal",
        "flags": _flags(),
    }


def summarize_cache(entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize supplied cache receipts without reading or mutating a cache."""
    rows = list(entries)[:256]
    hits = sum(1 for row in rows if bool(row.get("hit")))
    return {
        "ok": True,
        "state": "OBSERVED",
        "entries": len(rows),
        "hits": hits,
        "misses": len(rows) - hits,
        "cache_mutated": False,
        "telemetry_persisted": False,
        "authority": "cpu_cache_receipt_summary",
        "flags": _flags(),
    }


def module_status() -> dict[str, Any]:
    return {
        "ok": True,
        "state": "READY",
        "module": MODULE_ID,
        "version": VERSION,
        "manual_section": MANUAL_SECTION,
        "bounded": True,
        "read_only": True,
        "llm_authority": False,
        "flags": _flags(),
    }
