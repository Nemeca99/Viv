"""Focused regression tests for the read-only fractal CPU slice."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.fractal_core import allocate_spans, classify_query, emit_policies, module_status, propose_threshold, summarize_cache


def test_classification_is_bounded_and_deterministic() -> None:
    first = classify_query("Explain the UML pattern and why it works.")
    second = classify_query("Explain the UML pattern and why it works.")
    assert first == second
    assert first["ok"] is True
    assert abs(sum(first["mixture"].values()) - 1.0) < 0.00001
    assert first["flags"]["filesystem_write"] is False


def test_policy_allocation_respects_budget() -> None:
    policies = emit_policies({"logic": 1, "pattern_language": 1, "refactoring": 1, "meta": 1}, global_budget=20)
    result = allocate_spans(
        [{"id": "a", "cost": 10, "value": 10}, {"id": "b", "cost": 10, "value": 9}, {"id": "c", "cost": 9, "value": 8}],
        policies["global_budget"],
    )
    assert result["selected_cost"] <= 20
    assert result["value"] >= 18
    assert result["bounded"] is True


def test_threshold_and_cache_are_proposals_only() -> None:
    threshold = propose_threshold([{"success": 0.8}, {"success": 0.9}, {"success": "bad"}])
    cache = summarize_cache([{"hit": True}, {"hit": False}])
    assert threshold["applied"] is False
    assert cache["cache_mutated"] is False
    assert cache["telemetry_persisted"] is False


def test_no_forbidden_effects_or_model_imports() -> None:
    tree = ast.parse((ROOT / "lib" / "fractal_core.py").read_text(encoding="utf-8"))
    forbidden = {"subprocess", "socket", "requests", "torch", "numpy", "pathlib"}
    assert all(not isinstance(node, ast.ImportFrom) or node.module not in forbidden for node in ast.walk(tree))
    assert all(not isinstance(node, ast.Import) or all(alias.name not in forbidden for alias in node.names) for node in ast.walk(tree))


def test_module_status() -> None:
    result = module_status()
    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["llm_authority"] is False
