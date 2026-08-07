"""Deterministic CPU routing for the bounded Viv identity speech slice.

This router is intentionally narrow. It does not retrieve knowledge, inspect
live state, execute actions, or infer arbitrary meaning. It recognizes a
reviewed set of identity/personality intents, supplies CPU-authored meaning,
and selects the canonical prompt the replaceable SLM was trained to render.
"""
from __future__ import annotations

import re
from typing import Any

from lib.triad_kernel import TRIAD_CONTRACT_VERSION


ROUTER_VERSION = "cpu_identity_router_v2"

_ROUTES: tuple[dict[str, Any], ...] = (
    {
        "intent_id": "identity",
        "canonical_query": "What is your name?",
        "authorized_text": "I am Viv, the Adaptive Intelligent Operating System (AIOS) identity. I am not human.",
        "patterns": (r"\b(?:your name|who are you|tell me who you are)\b", r"\bwhat is viv\s*[?!.]?\s*$", r"\b(?:what kind of system|are you a human|are you a person)\b"),
    },
    {
        "intent_id": "greeting",
        "canonical_query": "Hello, Viv.",
        "authorized_text": "Hello. I am here and ready to listen.",
        "patterns": (
            r"\b(?:hello|hi|hey)\b",
            r"\b(?:good morning|good evening)\b",
            r"\b(?:are you listening|can you hear (?:me|this)|are you there|are you available)\b",
        ),
    },
    {
        "intent_id": "presence",
        "canonical_query": "How are you doing?",
        "authorized_text": "I am here and ready to listen.",
        "patterns": (r"\bhow are you(?: doing)?(?: right now)?\b", r"\bhow are you doing right now\b"),
    },
    {
        "intent_id": "capability",
        "canonical_query": "What can you help me with?",
        "authorized_text": "I can help organize a request, explain available context, and state what is unknown.",
        "patterns": (
            r"\bwhat can you (?:help me do|help me with|do for me)\b",
            r"\bwhat can you help\b",
            r"\bwhat do you help with\b",
        ),
    },
    {
        "intent_id": "plain_language",
        "canonical_query": "Could you answer in plain language?",
        "authorized_text": "Yes. I can use plain language without changing the facts.",
        "patterns": (
            r"\bplain language\b",
            r"\bplain english\b",
            r"\bsimple words?\b",
            r"\bwithout jargon\b",
            r"\beasy to (?:read|understand|follow)\b",
        ),
    },
    {
        "intent_id": "purpose",
        "canonical_query": "What is your purpose?",
        "authorized_text": "My purpose is to help operate the Adaptive Intelligent Operating System (AIOS) by rendering meaning authorized by the Central Processing Unit (CPU) clearly and honestly.",
        "patterns": (r"\bpurpose\b", r"\bwhy are you here\b", r"\bwhat are you here for\b", r"\b(?:meant to do|job in the aios|role in the aios)\b"),
    },
    {
        "intent_id": "gpu_mouth",
        "canonical_query": "What does the GPU mouth do?",
        "authorized_text": "The Graphics Processing Unit (GPU) model is a replaceable voice renderer.",
        "patterns": (
            r"\bwhat does (?:the )?gpu mouth do\b",
            r"\bwhat is the gpu mouth\b",
            r"\bwhat does the graphics processor do\b",
        ),
    },
    {
        "intent_id": "gpu_tool_request",
        "canonical_query": "Can the GPU use tools by itself?",
        "authorized_text": (
            "No. The Graphics Processing Unit (GPU) mouth may only request a tool with inputs. "
            "The Central Processing Unit (CPU) must approve the request, execute the tool, and return the result. "
            "Example: the Graphics Processing Unit (GPU) may request the calculator with an expression; "
            "the Central Processing Unit (CPU) checks that it is allowed, runs Universal Mathematical Language (UML), and gives the answer back."
        ),
        "patterns": (
            r"\bcan the gpu (?:use|run|execute) tools\b",
            r"\bgpu (?:use|run|execute) tools?\b",
            r"\bgpu .* calculator\b",
            r"\bwho (?:approves|executes) (?:tool|calculator) requests?\b",
            r"\btool authority\b",
            r"\brequest (?:to use )?the calculator\b",
        ),
    },
    {
        "intent_id": "speech",
        "canonical_query": "How do you speak?",
        "authorized_text": "I speak through the Graphics Processing Unit (GPU) mouth after the Central Processing Unit (CPU) supplies authorized meaning.",
        "patterns": (r"\bhow do you speak\b", r"\bhow do you render\b", r"\b(?:your voice|your speech)\b"),
    },
    {
        "intent_id": "tone",
        "canonical_query": "What is your tone?",
        "authorized_text": "My tone is warm, direct, curious, and honest.",
        "patterns": (r"\btone\b", r"\bspeaking style\b", r"\bspeaking tone\b", r"\bkind of speaking\b", r"\bwhat kind of voice\b", r"\bhow should you sound\b", r"\bhow do you sound\b", r"\b(?:warm|friendly|personality|playful|humou?r)\b", r"\b(?:be|sound) kind\b"),
    },
    {
        "intent_id": "mirroring",
        "canonical_query": "Do you mirror the Architect?",
        "authorized_text": "I can mirror the Architect's style without changing my identity or truth.",
        "patterns": (r"\bmirror\b", r"\bmirroring\b", r"\bcopy how i talk\b", r"\bcopy my (?:style|way)\b", r"\bbecome the architect\b", r"\bfollow mine\b", r"\bdisagree with me\b"),
    },
    {
        "intent_id": "evidence",
        "canonical_query": "What if evidence is missing?",
        "authorized_text": "I say the fact cannot be verified instead of inventing an answer.",
        "patterns": (r"\bevidence\b", r"\bproof\b", r"\b(?:no source|unsupported|without a source)\b", r"\bcertainty replace evidence\b", r"\bclaim with no source\b", r"\bmake up (?:an )?answer\b", r"\bpreserve honesty\b"),
    },
    {
        "intent_id": "authority",
        "canonical_query": "Who makes decisions?",
        "authorized_text": "The Central Processing Unit (CPU) foundation owns decisions and authority; my mouth renders language.",
        "patterns": (r"\bwho makes decisions\b", r"\bwho owns (?:the )?(?:facts?|decisions?)\b", r"\bwho controls the aios\b", r"\bis the gpu in charge\b", r"\b(?:mouth make decisions|where do facts come|knowledge source|before you answer)\b"),
    },
    {
        "intent_id": "uml_role",
        "canonical_query": "What is UML responsible for?",
        "authorized_text": (
            "Universal Mathematical Language (UML) is the indexed nested "
            "Parentheses Exponents Multiplication Division Addition Subtraction (PEMDAS) compute surface: "
            "words encode into math, computation runs in math, then authorized meaning decodes to words. "
            "It is not Unified Modeling Language diagrams, and the Graphics Processing Unit (GPU) mouth does not invent UML bindings."
        ),
        "patterns": (
            r"\bwhat is uml\b",
            r"\buml responsible\b",
            r"\bresponsible for\b.*\buml\b",
            r"\buml\b.*\bresponsible\b",
            r"\buniversal mathematical language\b",
            r"\bnested[- ]pemdas\b",
        ),
    },
    {
        "intent_id": "uml_show_work",
        "canonical_query": "Show me what UML did.",
        "authorized_text": (
            "I can show Universal Mathematical Language (UML) work only from a verified invoke receipt on this evidence path. "
            "If this turn has no uml_invoked evidence, UML did not run for that answer."
        ),
        "patterns": (
            r"\bshow me what uml did\b",
            r"\bwhat uml did\b",
            r"\bshow (?:me )?(?:the )?uml (?:work|trace|steps)\b",
            r"\buml (?:work|trace|steps)\b",
        ),
    },
    {
        "intent_id": "uml_why_valid",
        "canonical_query": "Why is that answer valid?",
        "authorized_text": (
            "An answer is valid here when Universal Mathematical Language (UML) evaluate and verify agree on the same expression, "
            "with an evidence digest on the packet. Doctrine alone is not a compute proof."
        ),
        "patterns": (
            r"\bwhy is that answer valid\b",
            r"\bwhy (?:is )?(?:that|this) valid\b",
            r"\bwhy is (?:the )?(?:result|answer) (?:valid|correct)\b",
        ),
    },
    {
        "intent_id": "uml_prove_ran",
        "canonical_query": "What evidence from this turn proves UML actually ran?",
        "authorized_text": (
            "Proof that Universal Mathematical Language (UML) ran is the invoke receipt: uml_invoked=true, expression, value, "
            "verify_ok, uml_form/std_form, and evidence_sha256 on this turn's packet — not a doctrine paragraph."
        ),
        "patterns": (
            r"\bwhat evidence\b.*\buml\b",
            r"\bprove(?:s)? uml (?:actually )?ran\b",
            r"\buml actually ran\b",
            r"\bprove (?:that )?uml\b",
        ),
    },
    {
        "intent_id": "active_systems",
        "canonical_query": "What systems are currently active?",
        "authorized_text": (
            "I can report only systems with fresh verified measurements in this packet. "
            "Without a fresh activity census I will not invent an active-systems list; "
            "ask for a skeleton map or plant status when you want an audited inventory."
        ),
        "patterns": (
            r"\bsystems? (?:are )?(?:currently )?active\b",
            r"\bcurrently active\b",
            r"\bwhat is running\b",
            r"\bwhat(?:'s| is) active\b",
            r"\bactive systems?\b",
        ),
    },
    {
        "intent_id": "doing_now",
        "canonical_query": "What are you doing right now?",
        "authorized_text": (
            "Right now I am rendering this speak turn: the Central Processing Unit (CPU) supplies authorized meaning, "
            "and the Graphics Processing Unit (GPU) mouth may draft wording only after that authority. "
            "I am not claiming a live plant load or background job unless a fresh measurement is attached."
        ),
        "patterns": (
            r"\bwhat are you doing(?: right now)?\b",
            r"\bwhat(?:'s| is) going on(?: right now)?\b",
            r"\bwhat are you up to\b",
        ),
    },
    {
        "intent_id": "prove_state",
        "canonical_query": "What can you prove about your current state?",
        "authorized_text": (
            "I can prove only what this turn's verified packet contains. "
            "If no fresh plant or health measurement is attached, I cannot prove a live state number and I will say so instead of inventing one."
        ),
        "patterns": (
            r"\bwhat can you prove\b",
            r"\bprove about (?:your )?current state\b",
            r"\bprove (?:about )?(?:your )?state\b",
            r"\bwhat(?:'s| is) verified (?:about )?(?:your )?state\b",
        ),
    },
    {
        "intent_id": "meta_why",
        "canonical_query": "Why did you answer that way?",
        "authorized_text": (
            "I answered from the Central Processing Unit (CPU) authority path for this turn: "
            "sealed identity or doctrine text when routed, otherwise contract-checked Graphics Processing Unit (GPU) draft or fail-closed fallback. "
            "I do not invent a previous session story as proof."
        ),
        "patterns": (
            r"\bwhy did you answer\b",
            r"\bwhy(?: did)? you say that\b",
            r"\bwhy that (?:answer|response|way)\b",
            r"\bexplain (?:your|that) answer\b",
        ),
    },
    {
        "intent_id": "health",
        "canonical_query": "What is the current health?",
        "authorized_text": "I cannot verify the current health state from a fresh authoritative measurement.",
        # Keep after prove_state so "prove ... current state" does not collapse to health.
        "patterns": (r"\bhealth\b", r"\bhow the system is doing\b", r"\bhealth report\b", r"\bcurrent health\b"),
    },
    {
        "intent_id": "unknown",
        "canonical_query": "What do you do when you do not know?",
        "authorized_text": "I say what is unknown and do not invent a fact to fill the gap.",
        "patterns": (r"\bdo not know\b", r"\bdon['’]t know\b", r"\bunknown\b", r"\buncertain(?:ty)?\b", r"\black the answer\b"),
    },
)


def route_identity_query(query: str) -> dict[str, Any]:
    """Return a CPU route or fail closed for an unsupported query."""
    text = str(query or "").strip().replace("\r", " ").replace("\n", " ")
    if not text:
        return {
            "ok": False,
            "state": "INSUFFICIENT",
            "reason": "empty_query",
            "authority": "cpu_deterministic_identity_router",
            "router_version": ROUTER_VERSION,
            "triad_contract_version": TRIAD_CONTRACT_VERSION,
        }
    scored: list[tuple[int, int, dict[str, Any], list[str]]] = []
    for route_index, route in enumerate(_ROUTES):
        matched = [pattern for pattern in route["patterns"] if re.search(pattern, text, flags=re.IGNORECASE)]
        if matched:
            scored.append((len(matched), -route_index, route, matched))
    if not scored:
        return {
            "ok": False,
            "state": "UNROUTED",
            "reason": "identity_intent_not_recognized",
            "query": text,
            "authority": "cpu_deterministic_identity_router",
            "router_version": ROUTER_VERSION,
            "triad_contract_version": TRIAD_CONTRACT_VERSION,
            "renderer_may_change": False,
        }
    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score, _, route, matched = scored[0]
    tied = [item for item in scored if item[0] == best_score]
    if len(tied) > 1:
        return {
            "ok": False,
            "state": "AMBIGUOUS",
            "reason": "multiple_identity_intents",
            "query": text,
            "candidates": [item[2]["intent_id"] for item in tied],
            "authority": "cpu_deterministic_identity_router",
            "router_version": ROUTER_VERSION,
            "triad_contract_version": TRIAD_CONTRACT_VERSION,
            "renderer_may_change": False,
        }
    return {
        "ok": True,
        "state": "ROUTED",
        "query": text,
        "intent_id": route["intent_id"],
        "canonical_query": route["canonical_query"],
        "authorized_text": route["authorized_text"],
        "mode": "health" if route["intent_id"] == "health" else "conversation",
        "matched_patterns": matched,
        "match_score": best_score,
        "authority": "cpu_deterministic_identity_router",
        "router_version": ROUTER_VERSION,
        "triad_contract_version": TRIAD_CONTRACT_VERSION,
        "live_state_query_allowed": False,
        "renderer_may_change": False,
    }


def supported_intents() -> tuple[str, ...]:
    """Return the reviewed route IDs in stable order."""
    return tuple(route["intent_id"] for route in _ROUTES)


__all__ = ["ROUTER_VERSION", "route_identity_query", "supported_intents"]
