"""CPU response planning boundary for the manual's ``luna_core``.

The planner decides how a response should be routed and budgeted.  It does
not generate facts or text.  A configured model/API may render the plan, but
retrieval and deterministic checks remain authoritative.
"""
from __future__ import annotations

import re
from typing import Any

from lib.consciousness_core import select_soul_fragment


MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.1 luna_core"

_TOKEN = re.compile(r"[a-z0-9_]{2,}")
_OPERATORS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("why", ("why", "cause", "reason")),
    ("how", ("how", "process", "steps", "way")),
    ("what", ("what", "define", "meaning")),
    ("where", ("where", "location")),
    ("when", ("when", "time", "date")),
    ("who", ("who", "person", "people")),
)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(str(text).casefold()))


def classify_traits(text: str) -> dict[str, Any]:
    tokens = _tokens(text)
    axes = {
        "analytical": {"explain", "analyze", "compare", "why", "how", "evidence", "truth"},
        "technical": {"code", "system", "implement", "algorithm", "test", "architecture"},
        "emotional": {"feel", "feeling", "support", "afraid", "sad", "angry", "love"},
        "creative": {"story", "creative", "imagine", "design", "dream", " art"},
    }
    scores = {name: len(tokens.intersection(words)) for name, words in axes.items()}
    ordered = sorted(scores, key=lambda name: (-scores[name], name))
    return {"scores": scores, "primary": ordered[0] if scores[ordered[0]] else "neutral", "authority": "cpu_deterministic_classifier"}


def linguistic_operator(text: str) -> dict[str, Any]:
    tokens = _tokens(text)
    scores = {name: len(tokens.intersection(words)) for name, words in _OPERATORS}
    selected = max(scores, key=lambda name: (scores[name], name))
    return {
        "operator": selected if scores[selected] else "statement",
        "scores": scores,
        "compression_hint": {"why": "causal_edges", "how": "mechanism_chain", "what": "type_classification", "where": "spatial_binding", "when": "temporal_binding", "who": "agent_aggregation"}.get(selected, "direct_statement"),
        "authority": "cpu_deterministic_classifier",
    }


def response_value(text: str) -> dict[str, Any]:
    tokens = _tokens(text)
    urgent = bool(tokens.intersection({"urgent", "emergency", "crisis", "critical", "safety"}))
    complexity = min(1.0, round((len(tokens) / 40.0) + (0.25 if "?" in text else 0.0), 4))
    if urgent:
        tier, target, maximum = "critical", 200, 400
    elif complexity >= 0.60 or len(tokens) >= 24:
        tier, target, maximum = "high", 100, 200
    elif complexity >= 0.25 or "?" in text:
        tier, target, maximum = "moderate", 50, 80
    else:
        tier, target, maximum = "trivial", 8, 15
    return {
        "tier": tier,
        "complexity": complexity,
        "emotional_stakes": "high" if urgent else "normal",
        "target_tokens": target,
        "max_tokens": maximum,
        "rule": "minimal_sufficient_response",
    }


def build_response_plan(text: str, *, grounded: bool = False, health_mode: bool = False) -> dict[str, Any]:
    """Build a typed plan; ``grounded`` is supplied by the retrieval gate."""
    fragment = select_soul_fragment(text)
    traits = classify_traits(text)
    operator = linguistic_operator(text)
    value = response_value(text)
    return {
        "ok": True,
        "fragment": fragment,
        "traits": traits,
        "linguistic_operator": operator,
        "response_value": value,
        "routing": {
            "gpu_or_api_role": "surface_rendering_only",
            "fact_authority": "retrieval_or_explicit_user_input" if grounded else "unverified_requires_abstention",
            "health_mode": bool(health_mode),
            "telemetry_in_ordinary_prompt": bool(health_mode),
        },
        "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
    }


def assess_rendered_response(text: str, *, grounded: bool) -> dict[str, Any]:
    """Small pre-output contract; it never claims semantic truth by itself."""
    clean = str(text).strip()
    leakage = any(marker in clean.casefold() for marker in ("master s_n", "rid=", "internal stability", "telemetry"))
    return {
        "ok": bool(clean) and not leakage,
        "nonempty": bool(clean),
        "telemetry_leakage": leakage,
        "grounding_required": not bool(grounded),
        "authority": "cpu_output_containment_check",
    }
