#!/usr/bin/env python3
"""Guarded U canonicalization — subtract unnecessary MD work.

Applies structural cancel seals such as (V*K)/K -> V when K != 0 and the
authoritative evaluation identity holds. Never invents bindings; never changes
arithmetic semantics. Fail-closed: if any seal check fails, leave the AST alone.

Federation dispatch (default ON after PASS_SUBTRACT_MD_DRAG):
  use ``federation_domains_for`` / ``federation_route_node`` so cancelable
  MD drag never reaches M/D experts. Override with UML_GUARDED_CANCEL=0.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any

from lib import uml_engine

_DOMAIN_KIND = {"add": "A", "sub": "S", "mul": "M", "div": "D"}
_SCALAR_KINDS = frozenset({"num", "var", "const"})

# Rules proved seal-safe on the MD shape census (0 failures). Integer
# recovery (V/K)*K is intentionally excluded until exact-division seal exists.
_SAFE_RULES = frozenset(
    {
        "cancel_mul_div_left_of_k",
        "cancel_mul_div_right_of_k",
        "cancel_mul_div_square",
        "cancel_k_over_k_times_v",
    }
)

# Default ON — A/B PASS_SUBTRACT_MD_DRAG. Env UML_GUARDED_CANCEL=0 disables.
_ENABLED: bool | None = None


def _env_enabled() -> bool:
    raw = os.environ.get("UML_GUARDED_CANCEL", "").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return False
    if raw in {"1", "true", "on", "yes"}:
        return True
    return True  # default on


def is_enabled() -> bool:
    global _ENABLED
    if _ENABLED is None:
        _ENABLED = _env_enabled()
    return bool(_ENABLED)


def set_enabled(enabled: bool) -> None:
    """Process-local override (tests / A/B baseline)."""
    global _ENABLED
    _ENABLED = bool(enabled)


def parse_without_observer(expr: str) -> tuple[Any, uml_engine.Node]:
    """Parse + eval_node without firing the evaluation observer."""
    text = str(expr).strip()
    notation = uml_engine.detect(text)
    if notation == "uml":
        node = uml_engine.UMLParser(text).parse()
    else:
        node = uml_engine.std_parse(text)
    return uml_engine.eval_node(node), node


def domains(node: uml_engine.Node) -> frozenset[str]:
    found: set[str] = set()

    def walk(current: uml_engine.Node) -> None:
        domain = _DOMAIN_KIND.get(current.kind)
        if domain:
            found.add(domain)
        for child in current.children:
            walk(child)

    walk(node)
    return frozenset(found)


def _unwrap(node: uml_engine.Node) -> uml_engine.Node:
    while node.kind in {"add", "sub", "mul", "div", "neutral"} and len(node.children) == 1:
        node = node.children[0]
    return node


def _scalar_key(node: uml_engine.Node) -> tuple[str, object] | None:
    if node.kind not in _SCALAR_KINDS or node.children:
        return None
    value = node.value
    if isinstance(value, complex) or value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return (node.kind, value)


def _scalar_node(value: object) -> uml_engine.Node:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return uml_engine.Node(kind="num", value=float(value) if isinstance(value, int) else value)


def _approx_eq(a: Any, b: Any) -> bool:
    return bool(uml_engine._approx_eq(a, b))


def shape_template(node: uml_engine.Node) -> str:
    """Normalize AST to a shape string; equal leaves share slots."""
    slots: dict[tuple[str, object], str] = {}
    next_id = 0

    def walk(current: uml_engine.Node) -> str:
        nonlocal next_id
        current = _unwrap(current)
        key = _scalar_key(current)
        if key is not None:
            if key not in slots:
                slots[key] = f"${next_id}"
                next_id += 1
            return slots[key]
        if current.kind == "neg":
            return f"neg({walk(current.children[0])})"
        if current.kind == "exp":
            exp = current.exp
            if isinstance(exp, float) and exp.is_integer():
                exp = int(exp)
            return f"exp({walk(current.children[0])},{exp})"
        if current.kind in {"add", "sub", "mul", "div"}:
            children: list[uml_engine.Node] = []
            if current.kind in {"add", "mul"}:
                for child in current.children:
                    if child.kind == current.kind:
                        children.extend(child.children)
                    else:
                        children.append(child)
            else:
                children = list(current.children)
            inner = ",".join(walk(child) for child in children)
            return f"{current.kind}({inner})"
        return f"{current.kind}[{len(current.children)}]"

    return walk(node)


def ast_symbolic_cost(node: uml_engine.Node) -> int:
    def walk(cur: uml_engine.Node) -> int:
        if not cur.children:
            return 1
        return 1 + sum(walk(child) for child in cur.children)

    return walk(node)


@dataclass(frozen=True)
class ReductionCandidate:
    rule_id: str
    reduced_to: str
    conditions: tuple[str, ...]
    description: str
    result_value: object


def classify_reduction(node: uml_engine.Node) -> ReductionCandidate | None:
    """Return a cancel candidate with extracted result value, or None."""
    node = _unwrap(node)

    if node.kind == "div" and len(node.children) == 2:
        num, den = node.children
        den_key = _scalar_key(den)
        if den_key is not None and num.kind == "mul" and len(num.children) == 2:
            a_key, b_key = _scalar_key(num.children[0]), _scalar_key(num.children[1])
            if a_key is not None and b_key is not None:
                k = den_key[1]
                if k == 0:
                    return None
                if a_key == den_key and b_key != den_key:
                    return ReductionCandidate(
                        rule_id="cancel_mul_div_right_of_k",
                        reduced_to="V",
                        conditions=("K!=0", "exact_output_identity"),
                        description="(K*V)/K -> V",
                        result_value=b_key[1],
                    )
                if b_key == den_key and a_key != den_key:
                    return ReductionCandidate(
                        rule_id="cancel_mul_div_left_of_k",
                        reduced_to="V",
                        conditions=("K!=0", "exact_output_identity"),
                        description="(V*K)/K -> V",
                        result_value=a_key[1],
                    )
                if a_key == den_key and b_key == den_key:
                    return ReductionCandidate(
                        rule_id="cancel_mul_div_square",
                        reduced_to="K",
                        conditions=("K!=0", "exact_output_identity"),
                        description="(K*K)/K -> K",
                        result_value=k,
                    )

    if node.kind == "mul" and len(node.children) == 2:
        left, right = node.children
        for a, b in ((left, right), (right, left)):
            if a.kind == "div" and len(a.children) == 2:
                num_key, den_key = _scalar_key(a.children[0]), _scalar_key(a.children[1])
                b_key = _scalar_key(b)
                if (
                    num_key is not None
                    and den_key is not None
                    and num_key == den_key
                    and b_key is not None
                    and b_key != num_key
                    and den_key[1] != 0
                ):
                    return ReductionCandidate(
                        rule_id="cancel_k_over_k_times_v",
                        reduced_to="V",
                        conditions=("K!=0", "exact_output_identity"),
                        description="V*(K/K) -> V",
                        result_value=b_key[1],
                    )
    return None


@dataclass(frozen=True)
class GuardedCancelResult:
    applied: bool
    rule_id: str | None
    description: str | None
    conditions: tuple[str, ...]
    original_expr: str
    reduced_expr: str | None
    original_node: uml_engine.Node
    reduced_node: uml_engine.Node | None
    original_domains: frozenset[str]
    reduced_domains: frozenset[str]
    original_cost: int
    reduced_cost: int | None
    authoritative_value: Any
    reduced_value: Any | None
    seal_ok: bool
    reject_reason: str | None


def try_guarded_cancel(
    expr: str,
    *,
    node: uml_engine.Node | None = None,
    authoritative_value: Any = None,
    require_md: bool = True,
) -> GuardedCancelResult:
    """Attempt seal-gated U cancel. Fail-closed on any mismatch.

    Uses parse+eval_node (not evaluate) when node/value are missing so this
    never re-enters the evaluation observer.
    """
    text = str(expr).strip()
    if node is None or authoritative_value is None:
        value, parsed = parse_without_observer(text)
        node = parsed if node is None else node
        if authoritative_value is None:
            authoritative_value = value

    original_domains = domains(node)
    original_cost = ast_symbolic_cost(node)
    base = GuardedCancelResult(
        applied=False,
        rule_id=None,
        description=None,
        conditions=(),
        original_expr=text,
        reduced_expr=None,
        original_node=node,
        reduced_node=None,
        original_domains=original_domains,
        reduced_domains=original_domains,
        original_cost=original_cost,
        reduced_cost=None,
        authoritative_value=authoritative_value,
        reduced_value=None,
        seal_ok=False,
        reject_reason=None,
    )

    if require_md and original_domains != {"M", "D"}:
        return replace(base, reject_reason="not_md_domain")

    candidate = classify_reduction(node)
    if candidate is None:
        return replace(base, reject_reason="no_safe_rule")

    if candidate.rule_id not in _SAFE_RULES:
        return replace(
            base,
            rule_id=candidate.rule_id,
            description=candidate.description,
            conditions=candidate.conditions,
            reject_reason="rule_not_in_safe_set",
        )

    # Hard condition: K != 0 is enforced inside classify; re-check via eval.
    reduced_node = _scalar_node(candidate.result_value)
    try:
        reduced_value = uml_engine.eval_node(reduced_node)
    except Exception as exc:  # noqa: BLE001
        return replace(
            base,
            rule_id=candidate.rule_id,
            description=candidate.description,
            conditions=candidate.conditions,
            reject_reason=f"reduced_eval_error:{type(exc).__name__}",
        )

    if not _approx_eq(authoritative_value, reduced_value):
        return replace(
            base,
            rule_id=candidate.rule_id,
            description=candidate.description,
            conditions=candidate.conditions,
            reduced_node=reduced_node,
            reduced_value=reduced_value,
            reject_reason="identity_mismatch",
        )

    reduced_expr = uml_engine.to_std(reduced_node)
    reduced_domains = domains(reduced_node)
    reduced_cost = ast_symbolic_cost(reduced_node)
    return GuardedCancelResult(
        applied=True,
        rule_id=candidate.rule_id,
        description=candidate.description,
        conditions=candidate.conditions,
        original_expr=text,
        reduced_expr=reduced_expr,
        original_node=node,
        reduced_node=reduced_node,
        original_domains=original_domains,
        reduced_domains=reduced_domains,
        original_cost=original_cost,
        reduced_cost=reduced_cost,
        authoritative_value=authoritative_value,
        reduced_value=reduced_value,
        seal_ok=True,
        reject_reason=None,
    )


def federation_route_node(
    expr: str,
    *,
    node: uml_engine.Node | None = None,
    authoritative_value: Any = None,
) -> tuple[uml_engine.Node, frozenset[str], GuardedCancelResult | None]:
    """Node + domains for federation dispatch after optional guarded cancel.

    When enabled and a seal-valid cancel applies, returns the reduced scalar
    node with empty arithmetic domains (no M/D federation). Fail-closed:
    identity mismatch leaves the original route untouched.
    """
    text = str(expr).strip()
    if node is None or authoritative_value is None:
        value, parsed = parse_without_observer(text)
        node = parsed if node is None else node
        if authoritative_value is None:
            authoritative_value = value

    if not is_enabled():
        return node, domains(node), None

    result = try_guarded_cancel(
        text,
        node=node,
        authoritative_value=authoritative_value,
        require_md=True,
    )
    if result.applied and result.seal_ok and result.reduced_node is not None:
        return result.reduced_node, result.reduced_domains, result
    return node, domains(node), result


def federation_domains_for(
    expr: str,
    *,
    node: uml_engine.Node | None = None,
    authoritative_value: Any = None,
) -> frozenset[str]:
    """Effective A/S/M/D domains after guarded U cancel (when enabled)."""
    _route_node, route_domains, _result = federation_route_node(
        expr,
        node=node,
        authoritative_value=authoritative_value,
    )
    return route_domains


__all__ = [
    "GuardedCancelResult",
    "ReductionCandidate",
    "ast_symbolic_cost",
    "classify_reduction",
    "domains",
    "federation_domains_for",
    "federation_route_node",
    "is_enabled",
    "parse_without_observer",
    "set_enabled",
    "shape_template",
    "try_guarded_cancel",
]
