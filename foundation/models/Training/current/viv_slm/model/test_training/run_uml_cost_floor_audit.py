#!/usr/bin/env python3
"""Prove whether a mixed route can beat mono/LIT under current UML cost.

This is a feasibility proof, not a model-accuracy test.

Current registry lane:
  - a sealed destination has a literal route;
  - ``uml_cost`` counts parsed AST nodes;
  - one literal is one AST node;
  - a route containing k distinct binary arithmetic domains needs at least
    k operator nodes and k+1 leaves, hence at least 2k+1 AST nodes.

Therefore every mixed route (k >= 2) has symbolic cost >= 5 and cannot be
strictly cheaper than the literal cost floor of 1. If the audit confirms the
premises across the live registry, the existing promotion comparison is
structurally infeasible in the sealed-destination encoding lane. A real winner
must be sought on a mixed *computation workload* where the result is not already
available as a literal before computation.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for path in (FOUNDATION, MODEL, SANDBOX):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.uml_equation_registry import (  # noqa: E402
    SANDBOX96_ARTIFACT,
    UMLEquationRegistry,
    _domains_in_expr,
    _symbolic_cost,
)

OUT_JSON = SANDBOX / "runs" / "uml_cost_floor_audit_latest.json"
OUT_MD = SANDBOX / "runs" / "uml_cost_floor_audit_latest.md"
GATE = SANDBOX / "uml_federation_promotion_gate.json"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"


def _federation(domains: frozenset[str]) -> str:
    return "".join(d for d in ("A", "S", "M", "D") if d in domains)


def audit() -> dict[str, Any]:
    registry = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    destinations = 0
    literal_floor_violations: list[dict[str, Any]] = []
    mixed_bound_violations: list[dict[str, Any]] = []
    strict_winners: list[dict[str, Any]] = []
    observed_min_by_width: dict[int, int] = {}
    mixed_routes = 0

    for char, entry in registry.entries.items():
        if not str(char).isprintable() or char in "\n\r\t":
            continue
        destinations += 1
        expressions = [str(entry["canonical"])] + [
            str(expr) for expr in (entry.get("equivalents") or [])
        ]
        unique = list(dict.fromkeys(expressions))

        literal_rows: list[tuple[str, int]] = []
        mixed_rows: list[tuple[str, int, str, int]] = []
        for expr in unique:
            try:
                cost = int(_symbolic_cost(expr))
            except Exception:
                continue
            domains = _domains_in_expr(expr)
            width = len(domains)
            if width == 0:
                literal_rows.append((expr, cost))
            if width >= 2:
                mixed_routes += 1
                federation = _federation(domains)
                mixed_rows.append((expr, cost, federation, width))
                prior = observed_min_by_width.get(width)
                observed_min_by_width[width] = cost if prior is None else min(prior, cost)
                theoretical = 2 * width + 1
                if cost < theoretical:
                    mixed_bound_violations.append(
                        {
                            "destination": char,
                            "expr": expr,
                            "federation": federation,
                            "width": width,
                            "cost": cost,
                            "theoretical_floor": theoretical,
                        }
                    )

        if not literal_rows:
            literal_floor_violations.append(
                {"destination": char, "kind": "missing_literal"}
            )
            continue
        literal_expr, literal_cost = min(
            literal_rows, key=lambda row: (row[1], len(row[0]), row[0])
        )
        if literal_cost != 1:
            literal_floor_violations.append(
                {
                    "destination": char,
                    "kind": "literal_cost_not_one",
                    "expr": literal_expr,
                    "cost": literal_cost,
                }
            )

        for expr, mixed_cost, federation, width in mixed_rows:
            if mixed_cost < literal_cost:
                strict_winners.append(
                    {
                        "destination": char,
                        "expr": expr,
                        "federation": federation,
                        "width": width,
                        "mixed_cost": mixed_cost,
                        "literal_expr": literal_expr,
                        "literal_cost": literal_cost,
                    }
                )

    premises_hold = (
        destinations > 0
        and not literal_floor_violations
        and not mixed_bound_violations
    )
    impossible = premises_hold and not strict_winners
    objective = (
        "PROVED_STRUCTURAL_IMPOSSIBILITY"
        if impossible
        else ("COUNTEREXAMPLE_FOUND" if strict_winners else "INCONCLUSIVE")
    )
    return {
        "objective": objective,
        "premises_hold": premises_hold,
        "sealed_destinations": destinations,
        "mixed_routes_scanned": mixed_routes,
        "literal_floor": 1,
        "mixed_theoretical_floor_by_width": {
            str(width): 2 * width + 1 for width in (2, 3, 4)
        },
        "mixed_observed_min_by_width": {
            str(width): cost for width, cost in sorted(observed_min_by_width.items())
        },
        "literal_floor_violations": literal_floor_violations,
        "mixed_bound_violations": mixed_bound_violations,
        "strict_winners": strict_winners,
        "conclusion": (
            "In the sealed-destination registry lane, mono/LIT is already the "
            "one-node answer. No truthful mixed expression can have cost below "
            "one. Expanding equivalent equations cannot produce a winner under "
            "this metric; doing so would game or redefine the gate."
            if impossible
            else "The live premises did not establish the expected impossibility."
        ),
        "next_valid_surface": (
            "A mixed computation workload where inputs are supplied and the "
            "destination literal does not exist until after execution. Compare "
            "persistent compiled composite vs dynamic U+foundations vs a "
            "materialized mono/LIT lookup over the same workload, including "
            "construction and storage amortized over a declared request window."
        ),
    }


def _sync(result: dict[str, Any], finished_at: str) -> None:
    if GATE.is_file():
        gate = json.loads(GATE.read_text(encoding="utf-8"))
        gate["cost_floor_audit"] = {
            "objective": result["objective"],
            "sealed_destination_lane_feasible": not (
                result["objective"] == "PROVED_STRUCTURAL_IMPOSSIBILITY"
            ),
            "receipt": str(OUT_JSON).replace("\\", "/"),
            "updated_at": finished_at,
        }
        GATE.write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if LATTICE.is_file():
        lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
        lattice["cost_floor_audit_latest"] = {
            "objective": result["objective"],
            "literal_floor": result["literal_floor"],
            "mixed_observed_min_by_width": result["mixed_observed_min_by_width"],
            "receipt": str(OUT_JSON).replace("\\", "/"),
            "updated_at": finished_at,
        }
        LATTICE.write_text(
            json.dumps(lattice, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if RECIPE.is_file():
        recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
        recipe["last_run"] = finished_at
        recipe["last_objective"] = result["objective"]
        recipe["cost_floor_audit"] = {
            "objective": result["objective"],
            "receipt": str(OUT_JSON).replace("\\", "/"),
        }
        if result["objective"] == "PROVED_STRUCTURAL_IMPOSSIBILITY":
            recipe["next_action"] = (
                "Benchmark the unchanged breakthrough comparison on a real mixed "
                "computation workload. Do not search for cheaper mixed equivalents "
                "inside a registry whose destination literal already costs one."
            )
        RECIPE.write_text(
            json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def main() -> int:
    result = audit()
    finished_at = datetime.now(timezone.utc).isoformat()
    receipt = {
        "schema_version": "uml_cost_floor_audit_v1",
        "status": "PASS",
        "finished_at": finished_at,
        **result,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# UML Cost-Floor Audit",
        "",
        f"- Objective: **{result['objective']}**",
        f"- Destinations: {result['sealed_destinations']}",
        f"- Mixed routes scanned: {result['mixed_routes_scanned']}",
        f"- Literal floor: {result['literal_floor']}",
        (
            "- Mixed observed minima (width 2/3/4): "
            f"{result['mixed_observed_min_by_width']}"
        ),
        f"- Strict mixed < LIT winners: {len(result['strict_winners'])}",
        "",
        result["conclusion"],
        "",
        f"Next valid surface: {result['next_valid_surface']}",
        "",
        f"Receipt: `{OUT_JSON.as_posix()}`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    _sync(result, finished_at)
    print(
        f"UML_COST_FLOOR_{result['objective']} "
        f"destinations={result['sealed_destinations']} "
        f"mixed={result['mixed_routes_scanned']} "
        f"winners={len(result['strict_winners'])}",
        flush=True,
    )
    return 0 if result["objective"] == "PROVED_STRUCTURAL_IMPOSSIBILITY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
