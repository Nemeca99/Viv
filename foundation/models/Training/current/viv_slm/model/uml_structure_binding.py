#!/usr/bin/env python3
"""Structure vs sealed identity binding for UML equations.

``A + A`` unbound is not wrong — it is incomplete. Deterministic structure:
``A + A = 2A``. Numeric collapse to ``2`` requires sealed binding ``A = 1``.
``1 + 1 = 2`` is already grounded; no identity may be invented.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[5]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib import uml_engine  # noqa: E402

_VAR_RE = re.compile(r"\?[A-Za-z0-9_]+")
_ADD_SAME = re.compile(
    r"^\s*(?P<a>\?[A-Za-z0-9_]+)\s*\+\s*(?P=a)\s*$"
)
_GROUNDED_RE = re.compile(r"^[\d+\-*/().\s]+$")


@dataclass
class BindingEnv:
    """Sealed identity bindings for UML variables (?name → value)."""

    bindings: dict[str, float] = field(default_factory=dict)

    def bind(self, name: str, value: float) -> None:
        key = name if name.startswith("?") else f"?{name}"
        self.bindings[key] = float(value)

    def get(self, name: str) -> float | None:
        key = name if name.startswith("?") else f"?{name}"
        return self.bindings.get(key)


def free_variables(expr: str) -> list[str]:
    return sorted(set(_VAR_RE.findall(str(expr))))


def is_grounded_numeric(expr: str) -> bool:
    s = str(expr).strip()
    return bool(s) and _GROUNDED_RE.match(s) is not None and not free_variables(s)


def structure_simplify_unbound(expr: str) -> dict[str, Any] | None:
    """Deterministic structure rules that do not invent bindings.

    Currently: identical unbound addends ``?X + ?X`` → ``2*?X``.
    """
    m = _ADD_SAME.match(str(expr))
    if not m:
        return None
    var = m.group("a")
    return {
        "kind": "unbound_structure",
        "input": str(expr).strip(),
        "structure_result": f"2*{var}",
        "free_variables": [var],
        "numeric_value": None,
        "invented_binding": False,
        "claim": "Unbound sum preserves structure; no identity guessed.",
    }


def evaluate_with_bindings(
    expr: str,
    env: BindingEnv | None = None,
    *,
    allow_invent: bool = False,
) -> dict[str, Any]:
    """Evaluate only with sealed bindings. Never invent missing identities.

    Returns structure result when unbound and a structure rule applies.
    Refuses numeric collapse when variables are free (unless allow_invent —
    which is forbidden for Viv and raises).
    """
    if allow_invent:
        raise ValueError("uml_binding_invent_forbidden")

    env = env or BindingEnv()
    text = str(expr).strip()
    frees = free_variables(text)
    unbound = [v for v in frees if env.get(v) is None]

    if is_grounded_numeric(text):
        value, _node, notation, _trace = uml_engine.evaluate(text)
        return {
            "kind": "grounded",
            "input": text,
            "structure_result": text,
            "numeric_value": value,
            "notation": notation,
            "free_variables": [],
            "invented_binding": False,
            "claim": "Fully grounded equation; result follows necessarily.",
        }

    if unbound:
        struct = structure_simplify_unbound(text)
        if struct is not None:
            return struct
        return {
            "kind": "unbound_incomplete",
            "input": text,
            "structure_result": None,
            "numeric_value": None,
            "free_variables": unbound,
            "invented_binding": False,
            "claim": (
                "Equation encoding incomplete: free variables lack sealed bindings. "
                "Arithmetic did not fail; identity was never provided."
            ),
            "status": "INCOMPLETE",
        }

    # All free vars sealed — substitute then evaluate.
    subst = text
    for name, val in env.bindings.items():
        subst = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", str(val), subst)
    value, _node, notation, _trace = uml_engine.evaluate(subst)
    return {
        "kind": "bound_grounded",
        "input": text,
        "substituted": subst,
        "structure_result": subst,
        "numeric_value": value,
        "notation": notation,
        "free_variables": frees,
        "bindings_used": {k: env.bindings[k] for k in frees},
        "invented_binding": False,
        "claim": "Sealed bindings applied; numeric result follows necessarily.",
    }


__all__ = [
    "BindingEnv",
    "evaluate_with_bindings",
    "free_variables",
    "is_grounded_numeric",
    "structure_simplify_unbound",
]
