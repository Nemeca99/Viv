#!/usr/bin/env python3
"""Build UML efficiency logit bias for speak_viv / sandwich paths."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from torch import Tensor

_FOUNDATION = Path(__file__).resolve().parents[5]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.uml_equation_registry import (  # noqa: E402
    SANDBOX96_ARTIFACT,
    UMLEquationRegistry,
)
from lib.uml_route_governor import (  # noqa: E402
    decide_route,
    make_generate_logits_bias_fn,
)

# Ordered: first match wins.
_TARGET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Prefer efficient UML for (.)", re.IGNORECASE),
    re.compile(r"Rank UML routes for (.)", re.IGNORECASE),
    re.compile(r"Is this UML valid for (.)\?", re.IGNORECASE),
    re.compile(r"UML equivalent for (.)", re.IGNORECASE),
    re.compile(r"equivalent for (.)", re.IGNORECASE),
    re.compile(r"UML encode long\nSurface: (.)", re.IGNORECASE),
    re.compile(r"UML encode\nSurface: (.)", re.IGNORECASE),
    re.compile(r"Surface: (.)", re.IGNORECASE),
    re.compile(r"What is the UML for ['\"]?(.)['\"]?", re.IGNORECASE),
    re.compile(r"UML for ['\"]?(.)['\"]?", re.IGNORECASE),
    re.compile(r"character\s+['\"]?(.)['\"]?", re.IGNORECASE),
    re.compile(r"char\s*=\s*['\"]?(.)['\"]?", re.IGNORECASE),
    re.compile(r"encode(?:\s+UML)?(?:\s+for)?\s+'(.)'", re.IGNORECASE),
    re.compile(r"encode(?:\s+UML)?(?:\s+for)?\s+(.)", re.IGNORECASE),
)

UML_DEFAULT_STOPS: tuple[str, ...] = ("\n", "<END>")


def clip_uml_equation_text(full_text: str, prompt: str) -> str:
    """Take generation after prompt, stop at first UML boundary."""
    text = str(full_text or "")
    p = str(prompt or "")
    if p and text.startswith(p):
        text = text[len(p) :]
    for stop in UML_DEFAULT_STOPS:
        if stop and stop in text:
            text = text.split(stop, 1)[0]
    return text.strip()


def infer_uml_target_from_prompt(
    prompt: str,
    *,
    vocab: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Infer fixed UML answer (char/value) from a speak prompt.

    Returns ``{target_char?, target_value?, method, matched}``.
    """
    text = str(prompt or "")
    vocab_set = set(vocab) if vocab is not None else None
    for pattern in _TARGET_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        ch = match.group(1)
        if vocab_set is not None and ch not in vocab_set:
            continue
        return {
            "target_char": ch,
            "target_value": None,
            "method": pattern.pattern,
            "matched": True,
        }
    return {
        "target_char": None,
        "target_value": None,
        "method": None,
        "matched": False,
    }


def load_default_registry(path: str | Path | None = None) -> UMLEquationRegistry:
    return UMLEquationRegistry.load(path or SANDBOX96_ARTIFACT)


def build_uml_speak_pressure(
    *,
    stoi: Mapping[str, int],
    itos: Mapping[int, str],
    prompt_len: int,
    target_char: str | None = None,
    target_value: int | None = None,
    prompt_text: str | None = None,
    auto_target: bool = True,
    proposals: Sequence[str] | None = None,
    registry: UMLEquationRegistry | None = None,
    registry_path: str | Path | None = None,
    scale: float = 6.0,
    hard_mask: bool = False,
    include_registry_pool: bool = True,
    complete_char: str = "\n",
) -> tuple[Callable[[Tensor, Tensor], Tensor], dict[str, Any]]:
    """Return ``(logits_bias_fn, receipt)`` for a fixed UML answer."""

    reg = registry or load_default_registry(registry_path)
    inferred = {
        "target_char": None,
        "target_value": None,
        "method": None,
        "matched": False,
    }
    if auto_target and target_char is None and target_value is None and prompt_text:
        inferred = infer_uml_target_from_prompt(prompt_text, vocab=reg.vocab)
        if inferred.get("matched"):
            target_char = inferred.get("target_char")  # type: ignore[assignment]

    if target_char is None and target_value is None:
        raise ValueError(
            "uml_speak_pressure_target_required:"
            "pass target_char/target_value or prompt_text with auto_target"
        )

    from lib.uml_thermal_route import decide_route_thermal

    thermal = decide_route_thermal(
        reg,
        target_char=target_char,
        target_value=target_value,
        proposals=list(proposals) if proposals else None,
        include_registry_pool=include_registry_pool,
    )
    if thermal.get("status") == "PASS" and thermal.get("pressure_weights"):
        pressure_weights = dict(thermal["pressure_weights"])
        decision_receipt = {
            "policy": "thermal_efficient_valid",
            "target_value": thermal.get("target_value"),
            "target_char": thermal.get("target_char"),
            "selected": thermal.get("selected"),
            "selected_cost": thermal.get("selected_symbolic_cost"),
            "selected_thermal_score": thermal.get("selected_thermal_score"),
            "valid_count": thermal.get("valid_count"),
            "plant": thermal.get("plant"),
            "diverged_from_symbolic_cheapest": thermal.get(
                "diverged_from_symbolic_cheapest"
            ),
        }
    else:
        decision = decide_route(
            reg,
            target_char=target_char,
            target_value=target_value,
            proposals=list(proposals) if proposals else None,
            include_registry_pool=include_registry_pool,
        )
        pressure_weights = decision.pressure_weights
        decision_receipt = {
            "policy": "cheapest_valid_fallback",
            "target_value": decision.target_value,
            "target_char": decision.target_char,
            "selected": decision.selected,
            "selected_cost": decision.selected_cost,
            "valid_count": decision.valid_count,
            "rejected_count": decision.rejected_count,
            "reason": decision.reason,
        }
    bias_fn = make_generate_logits_bias_fn(
        pressure_weights=pressure_weights,
        stoi=dict(stoi),
        itos=dict(itos),
        prompt_len=int(prompt_len),
        scale=float(scale),
        hard_mask=bool(hard_mask),
        complete_char=complete_char,
    )
    receipt = {
        "schema_version": "uml_speak_pressure_v3",
        "enabled": True,
        "scale": float(scale),
        "hard_mask": bool(hard_mask),
        "prompt_len": int(prompt_len),
        "auto_target": bool(auto_target),
        "inferred": inferred,
        "decision": decision_receipt,
    }
    return bias_fn, receipt


def prefer_efficient_prompt(prompt: str) -> bool:
    return bool(re.search(r"Prefer efficient UML for\s*.", str(prompt or ""), re.IGNORECASE))


def resolve_equation_for_policy(
    *,
    equation_text: str,
    prompt_text: str,
    registry: UMLEquationRegistry | None = None,
    policy: str = "auto",
) -> dict[str, Any]:
    """Post-generate route policy over a sealed destination.

    ``prefer_efficient`` / auto-on Prefer-efficient prompts: snap to the
    thermally efficient valid route (foundation master_rid × Nested-PEMDAS heat).
    Falls back to symbolic cheapest if thermal decide fails. Destination seal
    is preserved — this is route selection, not truth selection.
    """
    from lib.uml_thermal_route import decide_route_thermal

    reg = registry or load_default_registry()
    inferred = infer_uml_target_from_prompt(prompt_text, vocab=reg.vocab)
    ch = inferred.get("target_char")
    proposed = str(equation_text or "").strip()
    use_prefer = policy in ("prefer_efficient", "thermal_efficient") or (
        policy == "auto" and prefer_efficient_prompt(prompt_text)
    )
    if not use_prefer or not ch:
        return {
            "equation_text": proposed,
            "snapped": False,
            "policy": policy,
            "inferred": inferred,
        }
    thermal = decide_route_thermal(reg, target_char=str(ch), include_registry_pool=True)
    if thermal.get("status") == "PASS" and thermal.get("selected"):
        chosen = str(thermal["selected"])
        snapped = chosen != proposed
        return {
            "equation_text": chosen,
            "proposed": proposed,
            "snapped": snapped,
            "policy": "thermal_efficient",
            "inferred": inferred,
            "decision": {
                "selected": chosen,
                "selected_cost": thermal.get("selected_symbolic_cost"),
                "selected_thermal_score": thermal.get("selected_thermal_score"),
                "cheapest_symbolic": thermal.get("cheapest_symbolic"),
                "diverged_from_symbolic_cheapest": thermal.get(
                    "diverged_from_symbolic_cheapest"
                ),
                "target_char": thermal.get("target_char"),
                "valid_count": thermal.get("valid_count"),
                "plant": thermal.get("plant"),
            },
        }
    decision = decide_route(reg, target_char=str(ch), include_registry_pool=True)
    cheapest = str(decision.selected)
    snapped = cheapest != proposed
    return {
        "equation_text": cheapest,
        "proposed": proposed,
        "snapped": snapped,
        "policy": "prefer_efficient_fallback",
        "inferred": inferred,
        "decision": {
            "selected": decision.selected,
            "selected_cost": decision.selected_cost,
            "target_char": decision.target_char,
            "valid_count": decision.valid_count,
        },
    }


__all__ = [
    "UML_DEFAULT_STOPS",
    "build_uml_speak_pressure",
    "clip_uml_equation_text",
    "infer_uml_target_from_prompt",
    "load_default_registry",
    "prefer_efficient_prompt",
    "resolve_equation_for_policy",
]
