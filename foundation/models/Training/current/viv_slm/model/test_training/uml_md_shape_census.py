#!/usr/bin/env python3
"""Exact-shape census for U_MD evaluator traffic — no composite compile.

Classifies each MD-domain AST by normalized shape (leaf equality preserved as
slots) and whether a guarded structural reduction in U could replace the
federation entirely.

Shape rules live in ``lib.uml_guarded_canonicalize`` (shared with the A/B).
"""
from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from lib import uml_engine
from lib.uml_guarded_canonicalize import (
    ReductionCandidate,
    ast_symbolic_cost,
    classify_reduction as _classify_lib,
    domains,
    shape_template,
    try_guarded_cancel,
)


def classify_reduction(node: uml_engine.Node) -> ReductionCandidate | None:
    """Census wrapper: drop result_value when re-exporting the frozen candidate."""
    return _classify_lib(node)


def reduction_holds(
    node: uml_engine.Node,
    reduction: ReductionCandidate,
    authoritative: Any,
) -> dict[str, Any]:
    """Seal-check via the shared guarded cancel path."""
    result = try_guarded_cancel(
        "",
        node=node,
        authoritative_value=authoritative,
        require_md=True,
    )
    if reduction is None:
        return {"holds": False, "reason": "no_rule"}
    if result.applied and result.rule_id == reduction.rule_id:
        return {
            "holds": True,
            "v": result.reduced_value,
            "reason": None,
        }
    if result.reject_reason == "identity_mismatch":
        return {"holds": False, "reason": "value_mismatch"}
    if result.rule_id == reduction.rule_id and not result.applied:
        return {"holds": False, "reason": result.reject_reason or "rejected"}
    # Fallback: compare extracted result_value to authoritative.
    try:
        holds = bool(uml_engine._approx_eq(authoritative, reduction.result_value))
    except Exception:
        holds = False
    return {
        "holds": holds,
        "v": getattr(reduction, "result_value", None),
        "reason": None if holds else "value_mismatch",
    }


@dataclass
class ShapeStats:
    count: int = 0
    examples: list[str] = field(default_factory=list)
    reduction_rule: str | None = None
    reduction_description: str | None = None
    conditions: list[str] = field(default_factory=list)
    holds_count: int = 0
    fails_count: int = 0
    fail_reasons: Counter = field(default_factory=Counter)
    symbolic_costs: list[int] = field(default_factory=list)


class MDShapeCensusObserver:
    """Observe-only MD shape census; never selects or alters results."""

    def __init__(self, *, experiment_id: str, max_examples_per_shape: int = 3) -> None:
        self.experiment_id = experiment_id
        self.max_examples = max_examples_per_shape
        self._lock = threading.RLock()
        self._active = False
        self.total = 0
        self.md_total = 0
        self.by_shape: dict[str, ShapeStats] = {}
        self.non_md = 0

    def start(self) -> "MDShapeCensusObserver":
        with self._lock:
            if self._active:
                return self
            uml_engine.install_evaluation_observer(
                self,
                experiment_id=self.experiment_id,
                fail_closed=True,
            )
            self._active = True
        return self

    def stop(self) -> None:
        with self._lock:
            if not self._active:
                return
            uml_engine.remove_evaluation_observer(experiment_id=self.experiment_id)
            self._active = False

    def __call__(
        self,
        expr: str,
        node: uml_engine.Node,
        authoritative_value: Any,
        _notation: str,
    ) -> None:
        with self._lock:
            self.total += 1
            if domains(node) != {"M", "D"}:
                self.non_md += 1
                return
            self.md_total += 1
            template = shape_template(node)
            stats = self.by_shape.setdefault(template, ShapeStats())
            stats.count += 1
            if len(stats.examples) < self.max_examples:
                stats.examples.append(str(expr))
            # Never call uml_cost here: it re-enters evaluate() and inflates counts.
            stats.symbolic_costs.append(ast_symbolic_cost(node))
            reduction = classify_reduction(node)
            if reduction is not None:
                stats.reduction_rule = reduction.rule_id
                stats.reduction_description = reduction.description
                stats.conditions = list(reduction.conditions)
                check = reduction_holds(node, reduction, authoritative_value)
                if check.get("holds"):
                    stats.holds_count += 1
                else:
                    stats.fails_count += 1
                    stats.fail_reasons[str(check.get("reason") or "unknown")] += 1

    def summary(self) -> dict[str, Any]:
        with self._lock:
            shapes = []
            reducible = 0
            irreducible = 0
            reducible_invocations = 0
            for template, stats in sorted(
                self.by_shape.items(), key=lambda item: -item[1].count
            ):
                is_reducible = (
                    stats.reduction_rule is not None and stats.holds_count > 0
                )
                if is_reducible:
                    reducible += 1
                    reducible_invocations += stats.count
                else:
                    irreducible += 1
                mean_cost = (
                    sum(stats.symbolic_costs) / len(stats.symbolic_costs)
                    if stats.symbolic_costs
                    else None
                )
                shapes.append(
                    {
                        "shape": template,
                        "count": stats.count,
                        "share_of_md": stats.count / self.md_total if self.md_total else 0.0,
                        "examples": list(stats.examples),
                        "mean_symbolic_cost": mean_cost,
                        "reduction_rule": stats.reduction_rule,
                        "reduction_description": stats.reduction_description,
                        "conditions": list(stats.conditions),
                        "reduction_holds": stats.holds_count,
                        "reduction_fails": stats.fails_count,
                        "fail_reasons": dict(stats.fail_reasons),
                        "class": (
                            "reducible_by_u"
                            if is_reducible
                            else (
                                "reduction_candidate_failed_seal"
                                if stats.reduction_rule
                                else "irreducible_md"
                            )
                        ),
                    }
                )
            return {
                "evaluator_invocations": self.total,
                "md_invocations": self.md_total,
                "non_md_invocations": self.non_md,
                "distinct_shapes": len(shapes),
                "reducible_shapes": reducible,
                "irreducible_shapes": irreducible,
                "reducible_invocations": reducible_invocations,
                "irreducible_invocations": self.md_total - reducible_invocations,
                "reducible_share_of_md": (
                    reducible_invocations / self.md_total if self.md_total else 0.0
                ),
                "shapes": shapes,
                "note": (
                    "Counts are direct evaluator traffic only; symbolic cost uses "
                    "ast_symbolic_cost (no re-entrant evaluate)."
                ),
            }


__all__ = [
    "MDShapeCensusObserver",
    "ReductionCandidate",
    "classify_reduction",
    "domains",
    "reduction_holds",
    "shape_template",
]
