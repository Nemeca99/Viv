"""Read-only adapter for the CPU fractal planning slice."""
from __future__ import annotations

from typing import Any

from lib.cpu_fractal_reasoner import decompose
from lib.fractal_core import (
    allocate_spans,
    classify_query,
    emit_policies,
    module_status,
    propose_threshold,
    summarize_cache,
)


def status() -> dict[str, Any]:
    return module_status()


def cpu_plan(
    query: str,
    *,
    spans: list[dict[str, Any]] | None = None,
    observations: list[dict[str, Any]] | None = None,
    cache_entries: list[dict[str, Any]] | None = None,
    global_budget: int = 3500,
) -> dict[str, Any]:
    """Build a bounded plan from caller-supplied data only."""
    classification = classify_query(query)
    policies = emit_policies(classification.get("mixture") or {}, global_budget=global_budget)
    allocation = allocate_spans(spans or [], int(policies.get("global_budget", global_budget)), mixture=classification.get("mixture"))
    decomposition = decompose(query)
    threshold = propose_threshold(observations or [])
    cache = summarize_cache(cache_entries or [])
    return {
        "ok": bool(classification.get("ok")),
        "state": "VERIFIED" if classification.get("ok") else "INSUFFICIENT",
        "query": str(query),
        "classification": classification,
        "policies": policies,
        "allocation": allocation,
        "decomposition": decomposition,
        "threshold": threshold,
        "cache": cache,
        "applied": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def run_smoke() -> dict[str, Any]:
    result = cpu_plan(
        "Explain the pattern and test the bounded plan.",
        spans=[
            {"id": "explain", "cost": 10, "value": 8, "kind": "logic"},
            {"id": "test", "cost": 12, "value": 9, "kind": "refactoring"},
            {"id": "optional", "cost": 20, "value": 2, "kind": "meta"},
        ],
        observations=[{"success": 0.8}, {"success": 0.9}],
        cache_entries=[{"hit": True}, {"hit": False}],
        global_budget=22,
    )
    return {
        "ok": bool(result.get("ok") and result.get("allocation", {}).get("selected_cost", 0) <= 22),
        "state": "PASS" if result.get("ok") else "INCONCLUSIVE",
        "plan": result,
        "authority": "cpu_adapter_observation",
        "adapter_output_is_authority": False,
    }
