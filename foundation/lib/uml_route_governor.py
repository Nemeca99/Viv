#!/usr/bin/env python3
"""UML generation-time route governor.

Architecture (binding):
  probability  → route selection among candidates
  determinism  → evaluation / identity of the fixed answer
  efficiency   → among valid routes, prefer lowest uml_cost

Pipeline:
  Explore proposals → reject invalid → confirm fixed answer
  → keep cheapest valid path (argmax) OR pressure-sample among valid
  → optional char-level logit bias during LM generate.
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import torch
from torch import Tensor

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib import uml_engine  # noqa: E402
from lib.uml_equation_registry import (  # noqa: E402
    UMLEquationRegistry,
    _approx_eq,
    _eval_value,
    _symbolic_cost,
)

SCHEMA_VERSION = "uml_route_governor_v1.1"


@dataclass
class ScoredRoute:
    expr: str
    valid: bool
    value: float | None
    symbolic_cost: int | None
    length: int
    reject_reason: str | None = None
    source: str = "proposal"  # proposal | registry_pool


@dataclass
class RouteDecision:
    """Active decision pressure result for one fixed answer."""

    schema_version: str
    target_value: int
    target_char: str | None
    selected: str
    selected_cost: int
    reason: str
    valid_count: int
    rejected_count: int
    considered: list[ScoredRoute] = field(default_factory=list)
    pressure_weights: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


def _resolve_target(
    registry: UMLEquationRegistry,
    *,
    target_value: int | None,
    target_char: str | None,
) -> tuple[int, str | None]:
    if target_char is not None:
        if target_char not in registry.entries:
            raise KeyError(f"uml_route_unknown_char:{target_char!r}")
        value = int(registry.entries[target_char]["value"])
        if target_value is not None and int(target_value) != value:
            raise ValueError(
                f"uml_route_target_mismatch:char={target_char!r} "
                f"value={value} given={target_value}"
            )
        return value, target_char
    if target_value is None:
        raise ValueError("uml_route_target_required")
    value = int(target_value)
    ch = registry.value_to_char.get(value)
    return value, ch


def _score_expr(expr: str, *, target_value: int, source: str) -> ScoredRoute:
    text = str(expr).strip()
    if not text:
        return ScoredRoute(
            expr=text,
            valid=False,
            value=None,
            symbolic_cost=None,
            length=0,
            reject_reason="empty",
            source=source,
        )
    try:
        got = _eval_value(text)
    except Exception as exc:
        return ScoredRoute(
            expr=text,
            valid=False,
            value=None,
            symbolic_cost=None,
            length=len(text),
            reject_reason=f"eval_error:{type(exc).__name__}",
            source=source,
        )
    if not _approx_eq(got, float(target_value)):
        return ScoredRoute(
            expr=text,
            valid=False,
            value=float(got),
            symbolic_cost=None,
            length=len(text),
            reject_reason="value_mismatch",
            source=source,
        )
    try:
        cost = _symbolic_cost(text)
    except Exception as exc:
        return ScoredRoute(
            expr=text,
            valid=False,
            value=float(got),
            symbolic_cost=None,
            length=len(text),
            reject_reason=f"cost_error:{type(exc).__name__}",
            source=source,
        )
    return ScoredRoute(
        expr=text,
        valid=True,
        value=float(got),
        symbolic_cost=int(cost),
        length=len(text),
        reject_reason=None,
        source=source,
    )


def _registry_pool(registry: UMLEquationRegistry, target_value: int) -> list[str]:
    ch = registry.value_to_char.get(int(target_value))
    if ch is None:
        return [f"{int(target_value)}"]
    row = registry.entries[ch]
    pool = [str(row["canonical"]), *[str(x) for x in row.get("equivalents") or []]]
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for expr in pool:
        if expr not in seen:
            seen.add(expr)
            out.append(expr)
    return out


def _pressure_weights(valid: Sequence[ScoredRoute]) -> dict[str, float]:
    """Higher weight = cheaper route (for future logit / sampling pressure)."""
    if not valid:
        return {}
    raw: dict[str, float] = {}
    for row in valid:
        cost = int(row.symbolic_cost or 0)
        raw[row.expr] = 1.0 / float(cost + 1)
    total = sum(raw.values()) or 1.0
    return {k: v / total for k, v in raw.items()}


def decide_route(
    registry: UMLEquationRegistry,
    *,
    target_value: int | None = None,
    target_char: str | None = None,
    proposals: Sequence[str] | None = None,
    include_registry_pool: bool = True,
    policy: str = "cheapest_valid",
) -> RouteDecision:
    """Active route decision for a fixed answer.

    Parameters
    ----------
    proposals:
        Model- or operator-proposed equation routes (may be invalid).
    include_registry_pool:
        Also consider sealed registry canonical+equivalents for this value.
    policy:
        ``cheapest_valid`` (default) — lowest symbolic_cost, then shortest, then lex.
    """
    value, ch = _resolve_target(
        registry, target_value=target_value, target_char=target_char
    )
    considered: list[ScoredRoute] = []
    seen: set[str] = set()

    def add_many(exprs: Sequence[str], source: str) -> None:
        for expr in exprs:
            key = str(expr).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            considered.append(_score_expr(key, target_value=value, source=source))

    if proposals:
        add_many(list(proposals), "proposal")
    if include_registry_pool:
        add_many(_registry_pool(registry, value), "registry_pool")

    valid = [row for row in considered if row.valid and row.symbolic_cost is not None]
    rejected = [row for row in considered if not row.valid]

    if not valid:
        # Hard fallback: literal integer form (always evaluates for token ids).
        fallback = f"{value}"
        scored = _score_expr(fallback, target_value=value, source="fallback_literal")
        considered.append(scored)
        if not scored.valid or scored.symbolic_cost is None:
            raise RuntimeError(f"uml_route_no_valid_path:value={value}")
        valid = [scored]
        reason = "fallback_literal"
    else:
        reason = policy

    if policy != "cheapest_valid":
        raise ValueError(f"uml_route_policy_unsupported:{policy}")

    valid_sorted = sorted(
        valid,
        key=lambda row: (int(row.symbolic_cost or 10**9), row.length, row.expr),
    )
    chosen = valid_sorted[0]
    weights = _pressure_weights(valid_sorted)

    return RouteDecision(
        schema_version=SCHEMA_VERSION,
        target_value=value,
        target_char=ch,
        selected=chosen.expr,
        selected_cost=int(chosen.symbolic_cost or 0),
        reason=reason,
        valid_count=len(valid),
        rejected_count=len(rejected),
        considered=considered,
        pressure_weights=weights,
    )


def route_efficiency_error(
    registry: UMLEquationRegistry,
    *,
    proposed: str,
    target_value: int | None = None,
    target_char: str | None = None,
) -> dict[str, Any]:
    """Map a spoken/proposed route to a PID error in [0, 1].

    - invalid / non-matching value → error = 1.0 (bad route)
    - valid cheapest → error ≈ 0.0
    - valid but costly → error rises with (cost - cheapest) / (cost + 1)
    """
    value, ch = _resolve_target(
        registry, target_value=target_value, target_char=target_char
    )
    decision = decide_route(
        registry,
        target_value=value,
        target_char=ch,
        proposals=[proposed],
        include_registry_pool=True,
    )
    scored = _score_expr(str(proposed).strip(), target_value=value, source="proposal")
    cheapest_cost = int(decision.selected_cost)
    if not scored.valid or scored.symbolic_cost is None:
        error = 1.0
        kind = "invalid"
        cost = None
    else:
        cost = int(scored.symbolic_cost)
        # Relative inefficiency vs cheapest valid path for this fixed answer.
        error = float(max(0.0, cost - cheapest_cost) / float(cost + 1))
        kind = "valid_efficient" if cost <= cheapest_cost else "valid_costly"
    return {
        "schema_version": "uml_route_efficiency_error_v1",
        "proposed": str(proposed).strip(),
        "target_value": value,
        "target_char": ch,
        "valid": bool(scored.valid),
        "kind": kind,
        "reject_reason": scored.reject_reason,
        "proposed_cost": cost,
        "cheapest": decision.selected,
        "cheapest_cost": cheapest_cost,
        "error": float(min(1.0, max(0.0, error))),
    }


def route_cost_report(expr: str) -> dict[str, Any]:
    """Thin wrapper for operator inspection of a single path."""
    cost = uml_engine.uml_cost(expr)
    value, _node, notation, _trace = uml_engine.evaluate(expr)
    return {
        "expr": expr,
        "value": value if not isinstance(value, complex) else [value.real, value.imag],
        "notation": notation,
        "symbolic_cost": int(cost["symbolic_cost"]),
        "uml_cost": cost,
    }


def sample_route(
    registry: UMLEquationRegistry,
    *,
    target_value: int | None = None,
    target_char: str | None = None,
    proposals: Sequence[str] | None = None,
    include_registry_pool: bool = True,
    temperature: float = 1.0,
    generator: torch.Generator | None = None,
) -> RouteDecision:
    """Sample a valid route with efficiency pressure (not hard-argmax).

    ``temperature -> 0`` approaches cheapest_valid.
    ``temperature -> inf`` approaches uniform over valid routes.
    Weights come from ``1/(cost+1)`` then tempered as ``w ** (1/T)``.
    """
    base = decide_route(
        registry,
        target_value=target_value,
        target_char=target_char,
        proposals=proposals,
        include_registry_pool=include_registry_pool,
        policy="cheapest_valid",
    )
    weights = dict(base.pressure_weights)
    if not weights:
        return base
    exprs = list(weights.keys())
    raw = torch.tensor([weights[e] for e in exprs], dtype=torch.float64)
    temp = max(float(temperature), 1e-6)
    # Stable tempering: softmax(log(w) / T). T→0 ≈ argmax (cheapest mass).
    log_w = torch.log(raw.clamp_min(1e-12))
    tempered = torch.softmax(log_w / temp, dim=0)
    idx = int(torch.multinomial(tempered, num_samples=1, generator=generator).item())
    chosen = exprs[idx]
    # Recover cost from considered list
    cost = next(
        (
            int(row.symbolic_cost or 0)
            for row in base.considered
            if row.valid and row.expr == chosen
        ),
        int(base.selected_cost),
    )
    return RouteDecision(
        schema_version=SCHEMA_VERSION,
        target_value=base.target_value,
        target_char=base.target_char,
        selected=chosen,
        selected_cost=cost,
        reason=f"pressure_sample_T={temp:g}",
        valid_count=base.valid_count,
        rejected_count=base.rejected_count,
        considered=base.considered,
        pressure_weights=base.pressure_weights,
    )


def next_char_pressure_scores(
    pressure_weights: dict[str, float],
    prefix: str,
    *,
    complete_char: str = "\n",
) -> dict[str, float]:
    """Map next-character → summed route pressure for routes consistent with ``prefix``."""
    scores: dict[str, float] = {}
    for expr, weight in pressure_weights.items():
        w = float(weight)
        if not expr.startswith(prefix):
            continue
        if len(expr) == len(prefix):
            scores[complete_char] = scores.get(complete_char, 0.0) + w
            continue
        ch = expr[len(prefix)]
        scores[ch] = scores.get(ch, 0.0) + w
    return scores


def build_logit_bias(
    pressure_weights: dict[str, float],
    prefix: str,
    stoi: dict[str, int],
    *,
    vocab_size: int,
    scale: float = 4.0,
    hard_mask: bool = False,
    complete_char: str = "\n",
    device: torch.device | None = None,
    dtype: torch.dtype = torch.float32,
) -> Tensor:
    """Build a vocab-sized additive logit bias from route pressure.

    Soft mode: ``bias[tid] = scale * score`` for chars that continue at least
    one valid weighted route (higher pressure → higher logit).
    Hard mode: non-continuations get ``-inf`` once any continuation exists.
    """
    scores = next_char_pressure_scores(
        pressure_weights, prefix, complete_char=complete_char
    )
    bias = torch.zeros(vocab_size, device=device, dtype=dtype)
    if not scores:
        return bias
    for ch, score in scores.items():
        tid = stoi.get(ch)
        if tid is None:
            continue
        bias[int(tid)] = float(scale) * float(score)
    if hard_mask:
        allowed = {int(stoi[ch]) for ch in scores if ch in stoi}
        if allowed:
            mask = torch.ones(vocab_size, device=device, dtype=torch.bool)
            for tid in allowed:
                mask[tid] = False
            bias = bias.masked_fill(mask, float("-inf"))
    return bias


def make_generate_logits_bias_fn(
    *,
    pressure_weights: dict[str, float],
    stoi: dict[str, int],
    itos: dict[int, str],
    prompt_len: int,
    scale: float = 4.0,
    hard_mask: bool = False,
    complete_char: str = "\n",
) -> Callable[[Tensor, Tensor], Tensor]:
    """Factory for ``TransformerLanguageModel.generate(logits_bias_fn=...)``.

    Assumes generated suffix (after prompt) is the equation route being built.
    """

    def _fn(next_logits: Tensor, output_ids: Tensor) -> Tensor:
        # Batch 0 only for sandbox speak; broadcast if needed.
        row = output_ids[0].tolist()
        gen_ids = row[int(prompt_len) :]
        prefix = "".join(itos[int(tid)] for tid in gen_ids if int(tid) in itos)
        bias = build_logit_bias(
            pressure_weights,
            prefix,
            stoi,
            vocab_size=int(next_logits.shape[-1]),
            scale=scale,
            hard_mask=hard_mask,
            complete_char=complete_char,
            device=next_logits.device,
            dtype=next_logits.dtype,
        )
        return next_logits + bias.unsqueeze(0)

    return _fn


def govern_text_routes(
    registry: UMLEquationRegistry,
    text: str,
    *,
    proposals_per_char: Sequence[Sequence[str]] | None = None,
    include_registry_pool: bool = True,
    sample: bool = False,
    temperature: float = 1.0,
    generator: torch.Generator | None = None,
) -> dict[str, Any]:
    """Per-character active encode: fixed char → cheapest or pressure-sampled route."""
    decisions: list[dict[str, Any]] = []
    selected: list[str] = []
    for index, ch in enumerate(text):
        props = None
        if proposals_per_char is not None and index < len(proposals_per_char):
            props = list(proposals_per_char[index])
        if sample:
            decision = sample_route(
                registry,
                target_char=ch,
                proposals=props,
                include_registry_pool=include_registry_pool,
                temperature=temperature,
                generator=generator,
            )
        else:
            decision = decide_route(
                registry,
                target_char=ch,
                proposals=props,
                include_registry_pool=include_registry_pool,
            )
        selected.append(decision.selected)
        decisions.append(decision.to_dict())
    decoded = registry.decode_equations(selected)
    return {
        "schema_version": SCHEMA_VERSION,
        "surface_in": text,
        "routes": selected,
        "surface_out": decoded,
        "roundtrip_ok": decoded == text,
        "sample": bool(sample),
        "temperature": float(temperature) if sample else 0.0,
        "decisions": decisions,
    }
