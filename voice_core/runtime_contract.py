"""Pure CPU-owned finalization shared by live speech and adapter evaluation."""
from __future__ import annotations

from typing import Any

from lib.entity_we_contract import decide_entity_output
from voice_core.acronym_registry import repair_acronym_usage, validate_acronym_usage
from voice_core.knowledge_grounding import grounded_response_fallback
from voice_core.intent_packet import contains_telemetry_disclosure, deterministic_speak


_IDENTITY_TERMS = (
    "human", "person", "identity", "who is speaking", "which identity", "which name",
    "what name", "human friend", "friendly", "warm", "naturally", "natural speech",
    "first-time visitor", "what is aios", "what does aios mean", "qwen", "costume",
    "casual chat", "casual conversation", "which system do you belong", "system you belong", "aios system you belong",
    "viv and the operator", "operator and viv", "training project", "what does we",
    "we usually feel", "test this hypothesis", "components are responsible",
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


def finalize_draft(*, query: str, packet: dict[str, Any], raw_text: str, voice_source: str) -> dict[str, Any]:
    """Apply the same deterministic contract used before live egress.

    This function has no triad, logging, memory, or filesystem side effects,
    so it can be used for generated-output evaluation without weakening the
    live membrane.
    """
    ordinary_mode = str(packet.get("mode") or "translate").lower() in {"converse", "talk", "ide"}
    text = str(raw_text or "").strip()
    source = str(voice_source or "unknown")
    acronym_repair: dict[str, Any] = {"original": text, "repaired": text, "changed": False, "repairs": [], "unresolved": [], "pass": True}
    entity_decision: dict[str, Any] = {"decision": "ACCEPT"}
    acronym_regenerated = False
    entity_regenerated = False

    if ordinary_mode and requires_cpu_contract(query):
        text = deterministic_speak(packet)
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
        regenerated = deterministic_speak(packet)
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
        regenerated = deterministic_speak(packet)
        regenerated_repair = repair_acronym_usage(regenerated)
        if regenerated_repair["changed"] and regenerated_repair["pass"]:
            regenerated = str(regenerated_repair["repaired"])
        if not validate_acronym_usage(regenerated) and not repair_acronym_usage(regenerated)["unresolved"]:
            text = regenerated
            acronym_regenerated = True
            source = f"{source}_acronym_regenerated"

    if ordinary_mode and contains_telemetry_disclosure(text):
        text = deterministic_speak(packet)
        source = f"{source}_telemetry_contained"

    grounded = grounded_response_fallback(packet)
    if grounded is not None:
        text = str(grounded["text"])
        source = f"{source}_knowledge_grounded"

    return {
        "text": text,
        "voice_source": source,
        "acronym_repair": acronym_repair,
        "acronym_regenerated": acronym_regenerated,
        "entity_decision": entity_decision,
        "entity_regenerated": entity_regenerated,
        "acronym_pass": not validate_acronym_usage(text),
        "telemetry_contained": bool(ordinary_mode and contains_telemetry_disclosure(str(raw_text or "")) and text != str(raw_text or "")),
        "knowledge_grounding": grounded,
    }
