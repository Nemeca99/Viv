#!/usr/bin/env python3
"""UML codec I/O boundary — text outside, math tokens inside.

Binding:
  User text never trains the UML plant as language.
  Encode → Nested-PEMDAS equation tokens → model → decode → text.
  Math does not lie: a bad output means the equation/route was invalid or
  costly, not that arithmetic reinvented truth.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Sequence

_FOUNDATION = Path(__file__).resolve().parents[5]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.uml_equation_registry import (  # noqa: E402
    SANDBOX96_ARTIFACT,
    UMLEquationRegistry,
)
from lib.uml_route_governor import decide_route  # noqa: E402

EQ_SPLIT = re.compile(r"\s*,\s*")
MATH_CHARS = set("0123456789+-*/(). ")


def load_registry(path: str | Path | None = None) -> UMLEquationRegistry:
    return UMLEquationRegistry.load(path or SANDBOX96_ARTIFACT)


def encode_text_to_uml(
    text: str,
    *,
    registry: UMLEquationRegistry | None = None,
    prefer_efficient: bool = True,
) -> dict[str, Any]:
    """Lossless text → list of UML equations (one sealed char each)."""
    reg = registry or load_registry()
    surface = str(text)
    equations: list[str] = []
    for ch in surface:
        if ch not in reg.entries:
            raise KeyError(f"uml_codec_unknown_char:{ch!r}")
        if prefer_efficient:
            # Thermally efficient sealed route (foundation RID plant × Nested-PEMDAS heat).
            from lib.uml_thermal_route import decide_route_thermal

            thermal = decide_route_thermal(
                reg, target_char=ch, include_registry_pool=True
            )
            if thermal.get("status") == "PASS" and thermal.get("selected"):
                equations.append(str(thermal["selected"]))
            else:
                equations.append(str(reg.entries[ch]["canonical"]))
        else:
            equations.append(reg.encode_char(ch))
    joined = ",".join(equations)
    return {
        "schema_version": "uml_codec_encode_v1",
        "surface": surface,
        "equations": equations,
        "uml_stream": joined,
        "n_chars": len(surface),
        "prefer_efficient": bool(prefer_efficient),
        "roundtrip_ok": reg.decode_equations(equations) == surface,
    }


def decode_uml_to_text(
    equations: Sequence[str] | str,
    *,
    registry: UMLEquationRegistry | None = None,
) -> dict[str, Any]:
    """UML equation list / comma-stream → text (sealed identities)."""
    reg = registry or load_registry()
    if isinstance(equations, str):
        parts = [p for p in EQ_SPLIT.split(equations.strip()) if p]
    else:
        parts = [str(p).strip() for p in equations if str(p).strip()]
    text = reg.decode_equations(parts)
    return {
        "schema_version": "uml_codec_decode_v1",
        "equations": parts,
        "surface": text,
        "n_eq": len(parts),
    }


def is_math_token_surface(text: str) -> bool:
    """True if surface is equation-token material (digits/ops), not prose."""
    s = str(text).strip()
    if not s:
        return False
    # Allow commas as multi-eq separators and optional UML: header.
    body = s
    if body.upper().startswith("UML:"):
        body = body[4:].strip()
    return all(ch in MATH_CHARS or ch == "," for ch in body)


def build_native_uml_prompt(
    user_text: str,
    *,
    registry: UMLEquationRegistry | None = None,
    prefer_efficient: bool = True,
    response_marker: str = "Viv:",
) -> dict[str, Any]:
    """Build a model-facing prompt that is UML math tokens, not English prose.

    Outside: user_text (human).
    Inside: ``UML:<eq>,<eq>,...\\nViv:`` for the plant to continue in math.
    """
    enc = encode_text_to_uml(user_text, registry=registry, prefer_efficient=prefer_efficient)
    # Machine header only — not natural-language instruction.
    prompt = f"UML:{enc['uml_stream']}\n{response_marker} "
    return {
        "schema_version": "uml_native_prompt_v1",
        "user_text": user_text,
        "model_prompt": prompt,
        "encode": enc,
        "is_math_surface": is_math_token_surface(enc["uml_stream"]),
    }


def continue_uml_response(
    generated_suffix: str,
    *,
    registry: UMLEquationRegistry | None = None,
    n_expected: int | None = None,
    prefer_efficient: bool = True,
) -> dict[str, Any]:
    """Parse model UML continuation and decode to text; optional cheap snap per eq."""
    reg = registry or load_registry()
    raw = str(generated_suffix or "").strip()
    for stop in ("\n", "<END>"):
        if stop in raw:
            raw = raw.split(stop, 1)[0].strip()
    parts = [p for p in EQ_SPLIT.split(raw) if p]
    if n_expected is not None and len(parts) > n_expected:
        parts = parts[:n_expected]
    snapped = []
    final: list[str] = []
    for expr in parts:
        try:
            ch = reg.decode_eq(expr)
        except Exception as exc:
            return {
                "status": "FAIL",
                "error": f"decode:{expr!r}:{exc!r}",
                "raw": raw,
            }
        if prefer_efficient:
            from lib.uml_thermal_route import decide_route_thermal

            thermal = decide_route_thermal(
                reg, target_char=ch, include_registry_pool=True
            )
            if thermal.get("status") == "PASS" and thermal.get("selected"):
                chosen = str(thermal["selected"])
            else:
                decision = decide_route(reg, target_char=ch, include_registry_pool=True)
                chosen = str(decision.selected)
            snapped.append(chosen != expr)
            final.append(chosen)
        else:
            snapped.append(False)
            final.append(expr)
    dec = decode_uml_to_text(final, registry=reg)
    return {
        "status": "PASS",
        "raw": raw,
        "equations_proposed": parts,
        "equations_final": final,
        "snapped": snapped,
        "surface": dec["surface"],
        "decode": dec,
    }


def math_does_not_lie(
    proposed_expr: str,
    *,
    target_char: str,
    registry: UMLEquationRegistry | None = None,
) -> dict[str, Any]:
    """Classify fault: invalid equation vs valid costly route — never 'math lied'."""
    reg = registry or load_registry()
    from lib.uml_route_governor import route_efficiency_error

    info = route_efficiency_error(reg, proposed=proposed_expr, target_char=target_char)
    if not info.get("valid"):
        kind = "invalid_equation"
        claim = "The equation/question was wrong (or non-evaluating), not the arithmetic."
    elif info.get("kind") == "valid_efficient":
        kind = "valid_efficient"
        claim = "Equation seals the destination at cheapest cost."
    else:
        kind = "routing_fault"
        claim = "Equation seals the destination but is not the cheapest route."
    return {
        "schema_version": "uml_math_does_not_lie_v1",
        "proposed": proposed_expr,
        "target_char": target_char,
        "fault_kind": kind,
        "claim": claim,
        "route": info,
    }


__all__ = [
    "build_native_uml_prompt",
    "continue_uml_response",
    "decode_uml_to_text",
    "encode_text_to_uml",
    "is_math_token_surface",
    "load_registry",
    "math_does_not_lie",
]
