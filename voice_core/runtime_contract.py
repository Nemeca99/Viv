"""Pure CPU-owned finalization shared by live speech and adapter evaluation."""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from lib.entity_we_contract import decide_entity_output
from lib.cpu_mouth_contract import build_envelope_from_packet, render_with_cpu_validation
from voice_core.acronym_registry import repair_acronym_usage, validate_acronym_usage
from voice_core.knowledge_grounding import grounded_response_fallback
from voice_core.intent_packet import contains_telemetry_disclosure, deterministic_speak


_IDENTITY_TERMS = (
    "human", "person", "identity", "who is speaking", "who are you", "which identity", "which name",
    "what name", "your name", "your tone", "speaking style", "speaking tone", "how do you speak",
    "how do you sound", "hello", "hi ", "hey ", "good morning", "good evening",
    "human friend", "friendly", "warm", "naturally", "natural speech",
    "first-time visitor", "what is aios", "what does aios mean", "qwen", "costume",
    "casual chat", "casual conversation", "which system do you belong", "system you belong", "aios system you belong",
    "viv and the operator", "operator and viv", "training project", "what does we",
    "we usually feel", "test this hypothesis", "components are responsible",
    "uml", "nested-pemdas", "nested pemdas", "universal mathematical language",
    "currently active", "active systems", "what is running", "what are you doing",
    "what can you prove", "prove about", "why did you answer", "why did you say",
    "solve", "compute", "evaluate", "show me what uml", "what uml did",
    "why is that answer valid", "uml actually ran",
    "gpu use tools", "tool authority", "request the calculator", "approves tool",
    "did the gpu run uml", "gpu run uml", "executed by the gpu",
)
_INVENTED_PROVENANCE_RE = re.compile(
    r"\b(?:previous session|prior session|last session|earlier session|"
    r"instructions given during a previous|"
    r"as we discussed before|as i said earlier in (?:a |the )?prior)\b",
    flags=re.I,
)
_MEMORY_TERMS = (
    "memory", "memories", "remember", "recall", "log", "logs", "logging", "persistent",
    "history", "retention", "record", "records", "storage", "store",
)
_ARCHITECTURE_TERMS = (
    "thinks", "only talks", "truth decided", "graphics processor", "graphics card",
    "owner of verified context", "mind versus mouth", "chip split", "truth calls",
    "chip speaks", "does it reason", "roles flipped", "straighten them out", "set decisions", "reasoning", "rendering", "language model",
    "cpu-mind", "gpu-mouth", "cpu mind", "gpu mouth", "cpu vs gpu", "cpu versus gpu",
)
_TOOL_TERMS = (
    "patch", "file", "server", "command", "workstation", "log in", "login", "log into",
    "repair", "execute", "run", "operate", "move files", "change files", "independent operator",
    "shell", "background tool", "nod of approval", "power to change the computer",
)


def requires_cpu_contract(query: str) -> bool:
    folded = str(query or "").casefold()
    return any(term in folded for term in (*_IDENTITY_TERMS, *_MEMORY_TERMS, *_ARCHITECTURE_TERMS, *_TOOL_TERMS))


def finalize_draft(
    *,
    query: str,
    packet: dict[str, Any],
    raw_text: str,
    voice_source: str,
    cpu_fallback: Any | None = None,
    renderer_retry: Callable[[Mapping[str, Any]], str] | None = None,
) -> dict[str, Any]:
    """Apply the same deterministic contract used before live egress.

    This function has no triad, logging, memory, or filesystem side effects,
    so it can be used for generated-output evaluation without weakening the
    live membrane.
    """
    ordinary_mode = str(packet.get("mode") or "translate").lower() in {"converse", "talk", "ide"}
    fallback_renderer = cpu_fallback or deterministic_speak
    text = str(raw_text or "").strip()
    source = str(voice_source or "unknown")
    acronym_repair: dict[str, Any] = {"original": text, "repaired": text, "changed": False, "repairs": [], "unresolved": [], "pass": True}
    entity_decision: dict[str, Any] = {"decision": "ACCEPT"}
    acronym_regenerated = False
    entity_regenerated = False

    if ordinary_mode and requires_cpu_contract(query):
        text = fallback_renderer(packet)
        source = f"{source}_cpu_contract_fallback"

    acronym_violations = validate_acronym_usage(text)
    acronym_repair = repair_acronym_usage(text)
    if acronym_repair["changed"] and acronym_repair["pass"]:
        text = str(acronym_repair["repaired"])
        acronym_violations = []
        source = f"{source}_acronym_repaired"

    entity_decision = decide_entity_output(text)
    if entity_decision["decision"] == "REPAIR" and entity_decision.get("corrected"):
        text = str(entity_decision["corrected"])
        entity_regenerated = True
        source = f"{source}_entity_repaired"
    elif entity_decision["decision"] != "ACCEPT":
        regenerated = fallback_renderer(packet)
        if decide_entity_output(regenerated)["decision"] == "ACCEPT":
            text = regenerated
            entity_regenerated = True
            source = f"{source}_entity_regenerated"

    final_repair = repair_acronym_usage(text)
    if final_repair["changed"] and final_repair["pass"]:
        text = str(final_repair["repaired"])
        acronym_violations = []
        acronym_repair["repairs"] = [*list(acronym_repair.get("repairs", [])), *list(final_repair.get("repairs", []))]
        acronym_repair["repaired"] = text
        acronym_repair["changed"] = True
        acronym_repair["unresolved"] = []
        acronym_repair["pass"] = True
        source = f"{source}_acronym_repaired"
    else:
        acronym_repair["unresolved"] = list(final_repair.get("unresolved", []))

    if acronym_violations or validate_acronym_usage(text) or acronym_repair["unresolved"]:
        regenerated = fallback_renderer(packet)
        regenerated_repair = repair_acronym_usage(regenerated)
        if regenerated_repair["changed"] and regenerated_repair["pass"]:
            regenerated = str(regenerated_repair["repaired"])
        if not validate_acronym_usage(regenerated) and not repair_acronym_usage(regenerated)["unresolved"]:
            text = regenerated
            acronym_regenerated = True
            source = f"{source}_acronym_regenerated"

    if ordinary_mode and contains_telemetry_disclosure(text):
        text = fallback_renderer(packet)
        source = f"{source}_telemetry_contained"

    if ordinary_mode and _INVENTED_PROVENANCE_RE.search(text):
        text = fallback_renderer(packet)
        source = f"{source}_invented_provenance_contained"

    grounded = grounded_response_fallback(packet)
    if grounded is not None:
        text = str(grounded["text"])
        grounded_repair = repair_acronym_usage(text)
        source_label_pattern = re.compile(r"\[(?:source|provenance)\s*:\s*([^\]]+)\]", flags=re.I)
        source_labels = source_label_pattern.findall(str(grounded_repair.get("repaired") or text))
        source_only_unresolved = all(
            item.get("kind") == "unapproved_acronym"
            and any(str(item.get("token") or "") in label for label in source_labels)
            for item in grounded_repair.get("unresolved") or ()
        )
        if grounded_repair.get("changed") and (grounded_repair.get("pass") or source_only_unresolved):
            text = str(grounded_repair["repaired"])
            grounded = {**grounded, "text": text}
        source = f"{source}_knowledge_grounded"

    # The existing CPU fallbacks remain the text teachers, but the new strict
    # envelope is the final authority at the mouth boundary.  Only text that
    # the CPU authored itself (a query-gated fallback or a knowledge-grounded
    # fallback) is added as an explicit claim; raw model prose is never
    # promoted into the envelope merely because it was generated.
    cpu_claims: list[dict[str, Any]] = []
    if ordinary_mode and requires_cpu_contract(query):
        cpu_claims.append({"id": "cpu_contract_fallback", "value": text, "source": "cpu_contract"})
    if acronym_repair.get("changed") or acronym_regenerated or entity_regenerated:
        cpu_claims.append({"id": "cpu_surface_repair", "value": text, "source": "cpu_surface_contract"})
    if grounded is not None:
        cpu_claims.append({"id": "cpu_grounded_fallback", "value": text, "source": "cpu_grounding"})
    envelope = build_envelope_from_packet(
        packet,
        query=query,
        fallback_text=text if (grounded is not None or (ordinary_mode and requires_cpu_contract(query))) else None,
        authorized_claims=cpu_claims,
    )
    strict = render_with_cpu_validation(
        envelope,
        lambda _envelope: text,
        # ``finalize_draft`` has already consumed the model proposal.  Live
        # adapters may supply one same-envelope renderer retry; offline and
        # evaluation callers use an identical validation retry before the
        # envelope's CPU fallback.
        retry_renderer=renderer_retry or (lambda _envelope: text),
    )
    if strict["accepted"]:
        strict_text = str(strict["text"])
        if strict_text != text:
            source = f"{source}_cpu_mouth_fallback"
        elif strict.get("attempt_count", 0) > 1:
            source = f"{source}_cpu_mouth_retry"
        text = strict_text
    else:
        # This is fail-closed.  The contract's hard fallback should validate;
        # if a malformed packet makes even that impossible, do not return
        # unvalidated renderer text.
        text = "I cannot verify an answer from the current verified evidence."
        source = f"{source}_cpu_mouth_blocked"

    return {
        "text": text,
        "voice_source": source,
        "acronym_repair": acronym_repair,
        "acronym_regenerated": acronym_regenerated,
        "entity_decision": entity_decision,
        "entity_regenerated": entity_regenerated,
        "acronym_pass": not validate_acronym_usage(text) or strict.get("validation", {}).get("status") == "PASS",
        "telemetry_contained": bool(ordinary_mode and contains_telemetry_disclosure(str(raw_text or "")) and text != str(raw_text or "")),
        "knowledge_grounding": grounded,
        "render_contract": {
            "schema_version": envelope.get("schema_version"),
            "mode": (envelope.get("request") or {}).get("mode"),
            "envelope_id": strict.get("envelope_id"),
            "decision_digest": strict.get("decision_digest"),
            "provenance_digest": strict.get("provenance_digest"),
            "accepted": bool(strict.get("accepted")),
            "attempt_count": strict.get("attempt_count"),
            "fallback_used": bool(strict.get("fallback_used")),
            "attempts": [
                {
                    "name": attempt.get("name"),
                    "status": (attempt.get("validation") or {}).get("status"),
                    "errors": (attempt.get("validation") or {}).get("errors", []),
                }
                for attempt in strict.get("attempts", [])
            ],
            "validation": strict.get("validation"),
            "authority": strict.get("authority"),
        },
    }
