#!/usr/bin/env python3
"""Thermal-aware UML route selection — foundation RID plant + equation heat proxy.

Binding:
  - UML seals the destination token (tokenizer).
  - Among valid routes to that seal, prefer the path that is cheapest in
    Nested-PEMDAS cost AND lowest predicted thermal load.
  - Foundation ``master_rid`` (esp. coolant_loop / gpu / master_s_n) scales how
    aggressively we prefer cool routes during training/speak.
  - RID remains stability — it does not redefine the answer.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.uml_equation_registry import UMLEquationRegistry  # noqa: E402
from lib.uml_route_governor import (  # noqa: E402
    RouteDecision,
    ScoredRoute,
    decide_route,
    route_efficiency_error,
)

SCHEMA = "uml_thermal_route_v1"


def clamp01(x: float) -> float:
    return float(max(0.0, min(1.0, float(x))))


@dataclass
class PlantThermalView:
    master_s_n: float
    coolant_s_n: float | None
    gpu_s_n: float | None
    available: bool
    source: str
    raw: dict[str, Any] | None = None

    @property
    def thermal_stress(self) -> float:
        """0 = cool/healthy plant, 1 = stressed — amplifies cool-route preference."""
        base = 1.0 - clamp01(self.master_s_n)
        if self.coolant_s_n is not None:
            base = max(base, 1.0 - clamp01(self.coolant_s_n))
        if self.gpu_s_n is not None:
            base = max(base, 1.0 - clamp01(self.gpu_s_n))
        return clamp01(base)


def read_plant_thermal() -> PlantThermalView:
    """Read-only foundation master_rid thermal/stability snapshot."""
    try:
        from lib.master_rid import load_master_rid

        master = load_master_rid()
        if master is None:
            return PlantThermalView(
                master_s_n=0.5,
                coolant_s_n=None,
                gpu_s_n=None,
                available=False,
                source="master_rid_missing",
            )
        subs = master.subsystems if isinstance(master.subsystems, dict) else {}
        cool = subs.get("coolant_loop")
        gpu = subs.get("gpu")
        cool_s = float(cool.s_n) if cool is not None and getattr(cool, "available", False) else None
        gpu_s = float(gpu.s_n) if gpu is not None and getattr(gpu, "available", False) else None
        # load_master_rid may return dataclass or dict-like
        if hasattr(master, "master_s_n"):
            ms = float(master.master_s_n)
            raw = master.to_dict() if hasattr(master, "to_dict") else None
        else:
            ms = float(master.get("master_s_n", 0.5))  # type: ignore[union-attr]
            raw = dict(master) if isinstance(master, dict) else None
        return PlantThermalView(
            master_s_n=ms,
            coolant_s_n=cool_s,
            gpu_s_n=gpu_s,
            available=True,
            source="master_rid",
            raw=raw,
        )
    except Exception as exc:
        return PlantThermalView(
            master_s_n=0.5,
            coolant_s_n=None,
            gpu_s_n=None,
            available=False,
            source=f"master_rid_error:{exc!r}",
        )


def equation_heat_proxy(expr: str) -> dict[str, Any]:
    """Predict thermal load of an equation from Nested-PEMDAS structure (no GPU stress).

    Uses the same nesting×math product as training ``uml_nested_pemdas_leaves``
    (x_in * x_out) via foundation ``uml_cost`` — no viv_slm import required.
    """
    from lib import uml_engine

    cost = uml_engine.uml_cost(expr)
    nesting_scale = 12.0
    math_scale = 10.0
    x_in = clamp01(float(cost["max_depth"]) / nesting_scale)
    x_out = clamp01(float(cost["symbolic_cost"]) / math_scale)
    heat = clamp01(x_in * x_out)
    return {
        "expr": expr,
        "heat": heat,
        "x_in": x_in,
        "x_out": x_out,
        "symbolic_cost": float(cost["symbolic_cost"]),
        "max_depth": int(cost["max_depth"]),
        "ast_nodes": int(cost.get("ast_nodes") or 0),
        "source": "uml_engine.uml_cost",
    }


def thermal_route_score(
    expr: str,
    *,
    plant: PlantThermalView | None = None,
) -> dict[str, Any]:
    """Lower is better: heat amplified when plant thermal stress is high."""
    plant = plant or read_plant_thermal()
    heat_info = equation_heat_proxy(expr)
    stress = plant.thermal_stress
    # When plant is cool (stress~0), heat still ranks routes; when hot, amplify.
    score = float(heat_info["heat"]) * (1.0 + stress)
    return {
        "expr": expr,
        "score": score,
        "heat": heat_info["heat"],
        "plant_stress": stress,
        "plant_master_s_n": plant.master_s_n,
        "plant_available": plant.available,
        "heat_info": heat_info,
    }


def decide_route_thermal(
    registry: UMLEquationRegistry,
    *,
    target_value: int | None = None,
    target_char: str | None = None,
    proposals: Sequence[str] | None = None,
    include_registry_pool: bool = True,
    plant: PlantThermalView | None = None,
) -> dict[str, Any]:
    """Among valid sealed routes, pick lowest thermal score (then symbolic cost).

    Destination remains sealed by ``decide_route`` validity — thermal only ranks
    valid members of the equivalence class.
    """
    plant = plant or read_plant_thermal()
    base = decide_route(
        registry,
        target_value=target_value,
        target_char=target_char,
        proposals=proposals,
        include_registry_pool=include_registry_pool,
        policy="cheapest_valid",
    )
    valid = [r for r in base.considered if r.valid and r.symbolic_cost is not None]
    if not valid:
        return {
            "schema_version": SCHEMA,
            "status": "FAIL",
            "reason": "no_valid_routes",
            "base": base.to_dict(),
            "plant": {
                "master_s_n": plant.master_s_n,
                "thermal_stress": plant.thermal_stress,
                "available": plant.available,
                "source": plant.source,
            },
        }

    ranked: list[dict[str, Any]] = []
    for row in valid:
        ts = thermal_route_score(row.expr, plant=plant)
        ranked.append(
            {
                "expr": row.expr,
                "symbolic_cost": int(row.symbolic_cost or 0),
                "length": row.length,
                "thermal_score": ts["score"],
                "heat": ts["heat"],
                "source": row.source,
            }
        )
    ranked.sort(key=lambda r: (r["thermal_score"], r["symbolic_cost"], r["length"], r["expr"]))
    chosen = ranked[0]
    # Pressure weights: cooler routes get higher weight.
    inv = [1.0 / (r["thermal_score"] + 1e-6) for r in ranked]
    total = sum(inv) or 1.0
    weights = {r["expr"]: inv[i] / total for i, r in enumerate(ranked)}

    return {
        "schema_version": SCHEMA,
        "status": "PASS",
        "policy": "thermal_efficient_valid",
        "target_char": base.target_char,
        "target_value": base.target_value,
        "selected": chosen["expr"],
        "selected_symbolic_cost": chosen["symbolic_cost"],
        "selected_thermal_score": chosen["thermal_score"],
        "cheapest_symbolic": base.selected,
        "cheapest_symbolic_cost": base.selected_cost,
        "diverged_from_symbolic_cheapest": chosen["expr"] != base.selected,
        "valid_count": len(valid),
        "ranked": ranked[:12],
        "pressure_weights": weights,
        "plant": {
            "master_s_n": plant.master_s_n,
            "coolant_s_n": plant.coolant_s_n,
            "gpu_s_n": plant.gpu_s_n,
            "thermal_stress": plant.thermal_stress,
            "available": plant.available,
            "source": plant.source,
        },
        "seal_ok": True,
    }


def compare_equations_thermal(
    registry: UMLEquationRegistry,
    equations: Sequence[str],
    *,
    target_char: str | None = None,
    target_value: int | None = None,
    plant: PlantThermalView | None = None,
) -> dict[str, Any]:
    """Compare candidate equations: validity/seal + thermal ranking for training."""
    plant = plant or read_plant_thermal()
    rows = []
    for expr in equations:
        info = route_efficiency_error(
            registry, proposed=expr, target_char=target_char, target_value=target_value
        )
        ts = thermal_route_score(expr, plant=plant) if info.get("valid") else None
        rows.append(
            {
                "expr": expr,
                "valid": bool(info.get("valid")),
                "kind": info.get("kind"),
                "error": info.get("error"),
                "thermal_score": None if ts is None else ts["score"],
                "heat": None if ts is None else ts["heat"],
            }
        )
    valid_rows = [r for r in rows if r["valid"] and r["thermal_score"] is not None]
    valid_rows.sort(key=lambda r: (float(r["thermal_score"]), r["expr"]))
    return {
        "schema_version": SCHEMA,
        "plant_stress": plant.thermal_stress,
        "plant_master_s_n": plant.master_s_n,
        "rows": rows,
        "best_thermal_valid": valid_rows[0] if valid_rows else None,
    }


__all__ = [
    "PlantThermalView",
    "compare_equations_thermal",
    "decide_route_thermal",
    "equation_heat_proxy",
    "read_plant_thermal",
    "thermal_route_score",
]
