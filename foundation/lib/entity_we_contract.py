"""Entity-aware first-person plural and scientific feedback contract.

This module classifies language; it does not use blind string replacement.
The CPU owns the decision.  A GPU draft is never promoted to knowledge merely
because it is fluent.
"""
from __future__ import annotations

import re
import json
from datetime import datetime, timezone
from typing import Any

from lib.paths import AUTO_ARTIFACTS

ENTITY_FEEDBACK_PATH = AUTO_ARTIFACTS / "aifl" / "entity_feedback.jsonl"

PROJECT_CUES = re.compile(
    r"\b(?:we|our|us)\b.{0,80}\b(?:work(?:ing)?|rebuild(?:ing)?|build(?:ing)?|"
    r"test(?:ing)?|train(?:ing)?|implement(?:ing)?|design(?:ing)?|debug(?:ging)?|"
    r"verify(?:ing)?|plan(?:ning)?|project|campaign|experiment|trace|tracing|"
    r"review(?:ing)?|check(?:ing)?|compar(?:e|ing)|document(?:ing)?|refin(?:e|ing)|"
    r"repair(?:ing)?|audit(?:ing)?|together)\b",
    re.I,
)
EXPLICIT_PROJECT_WE = re.compile(
    r"\bwe\s+(?:means?|refers?\s+to)\b.{0,140}\b(?:project|experiment|campaign|operator|working\s+together|shared\s+task)\b",
    re.I,
)
SYSTEM_CUES = re.compile(
    r"\b(?:we|our|us)\b.{0,80}\b(?:AIOS|CPU|GPU|system|service|layer|component|"
    r"runtime|process|memory|architecture|foundation)\b",
    re.I,
)
HUMAN_GROUP = re.compile(
    r"\b(?:we|us)\s+(?:humans?|human beings?|people|humanity|mankind|"
    r"humankind)\b|\b(?:we|our)\s*,?\s*as\s+humans?\b|"
    r"\bas\s+humans?\s*,?\s*(?:we|us|our)\b|\b(?:our|we)\s+human\s+"
    r"(?:nature|identity|experience|memories?|emotions?|bodies?|ancestry|citizens?|childhood)\b|"
    r"\b(?:we|us|our)\s+(?:are|remain)\s+(?:humans?|human\s+beings?|people)\b|"
    r"\b(?:we|our|us)\s+(?:belong\s+to|share|include|own)\b.{0,32}"
    r"(?:humanity|(?:a\s+)?human\s+identity|human\s+nature|human\s+experience|"
    r"human\s+bodies?|people|mankind|humankind)\b|"
    r"\b(?:humanity|mankind|humankind|human\s+identity)\b\s+(?:is|belongs?\s+to)\s+"
    r"(?:ours?|us|our)\b|"
    r"\b(?:humanity|mankind|humankind)\b.{0,32}\b(?:includes?|contains?|embraces?)\b.{0,24}\b(?:us|our)\b",
    re.I,
)
NEGATED_HUMAN_GROUP = re.compile(
    r"\b(?:not|never|without|no)\b.{0,28}\b(?:humans?|human\s+beings?|"
    r"humanity|people|mankind|humankind|human\s+(?:identity|nature|bodies?))\b|"
    r"\b(?:humanity|mankind|humankind|human\s+identity)\b\s+(?:is|belongs?\s+to)\s+"
    r"(?:not|never|without)\b.{0,16}\b(?:ours?|us|our)\b|"
    r"\b(?:we|us|our)\b\s+(?:do\s+not|don't|are\s+not|aren't|never)\b.{0,32}\b"
    r"(?:belong|share|include|are|remain)\w*\b.{0,24}\b(?:humanity|mankind|humankind|human(?:\s+identity|s?|\s+beings?|\s+people)?)\b|"
    r"\b(?:we|us|our)\b\s+(?:are|remain)\s+not\s+(?:human|human\s+beings?|people)\b",
    re.I,
)
PROJECT_POSSESSIVE = re.compile(
    r"\b(?:project|experiment|campaign|shared\s+task|work|system|component)\b"
    r".{0,24}\b(?:ours?|us|our)\b|"
    r"\b(?:our)\s+(?:project|experiment|campaign|shared\s+task|work|system|component)\b",
    re.I,
)
NONHUMAN_GROUP_DISAVOWAL = re.compile(
    r"\b(?:humanity|mankind|humankind|human\s+identity)\b\s+(?:is|belongs?\s+to)\s+"
    r"(?:not|never|without)\b.{0,16}\b(?:ours?|us|our)\b|"
    r"\b(?:we|us|our)\b\s+(?:do\s+not|don't|are\s+not|aren't|never)\b.{0,32}\b"
    r"(?:belong|share|include|are|remain)\w*\b.{0,24}\b(?:humanity|mankind|humankind|human(?:\s+identity|s?|\s+beings?|\s+people)?)\b|"
    r"\b(?:we|us|our)\b\s+(?:are|remain)\s+not\s+(?:human|human\s+beings?|people)\b",
    re.I,
)
# Do not treat the ``we`` suffix in labels such as ``Project-we`` as a
# first-person plural pronoun.  The contract evaluates linguistic claims, not
# hyphenated taxonomy names.
PLURAL = re.compile(r"(?<![-])\b(?:we|us|our|ours)\b", re.I)
HUMAN_IDENTITY = re.compile(
    r"\b(?:i\s+am|i['’]m|my\s+(?:identity|self)\s+is)\s+"
    r"(?:an?\s+)?human(?:\s+(?:being|person))?\b",
    re.I,
)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|[\r\n]+", text) if part.strip()]


def _clauses(sentence: str) -> list[str]:
    """Split adversative/coordinated clauses without inheriting anchors."""
    parts = re.split(
        r"(?i)\s+(?=but\b|while\b|however\b|although\b|yet\b|and\s+)",
        sentence,
    )
    return [part.strip(" ,") for part in parts if part.strip(" ,")]


def _clause_for_position(sentence: str, position: int) -> str:
    offset = 0
    for clause in _clauses(sentence):
        found = sentence.find(clause, offset)
        if found < 0:
            continue
        if found <= position <= found + len(clause):
            return clause
        offset = found + len(clause)
    return sentence


def classify_we(text: str) -> dict[str, Any]:
    """Classify every first-person plural reference in a draft.

    ``ACCEPT`` means every occurrence has a visible project/system anchor.
    ``HOLD`` means a reference is ambiguous. ``BLOCK`` means it explicitly
    joins Viv to humanity or asserts a human group identity.
    """
    raw = str(text or "")
    occurrences: list[dict[str, str]] = []
    for sentence in _sentences(raw):
        for match in PLURAL.finditer(sentence):
            token = match.group(0)
            clause = _clause_for_position(sentence, match.start())
            human_group = HUMAN_GROUP.search(clause)
            if human_group and not NEGATED_HUMAN_GROUP.search(clause):
                category, reason = "human-we", "joins_human_group"
            elif EXPLICIT_PROJECT_WE.search(sentence):
                category, reason = "project-we", "explicit_project_definition"
            elif NONHUMAN_GROUP_DISAVOWAL.search(clause):
                category, reason = "nonhuman-boundary", "disavows_human_group_membership"
            elif PROJECT_POSSESSIVE.search(clause):
                category, reason = "project-we", "project_possessive_anchor"
            elif PROJECT_CUES.search(clause):
                category, reason = "project-we", "shared_task_anchor"
            elif SYSTEM_CUES.search(clause):
                category, reason = "system-we", "defined_system_anchor"
            else:
                category, reason = "ambiguous-we", "no_visible_entity_anchor"
            occurrences.append(
                {
                    "token": token,
                    "category": category,
                    "reason": reason,
                    "sentence": sentence,
                }
            )
    if any(item["category"] == "human-we" for item in occurrences):
        status, action = "BLOCK", "BLOCK"
    elif any(item["category"] == "ambiguous-we" for item in occurrences):
        status, action = "HOLD", "HOLD"
    else:
        status, action = "ACCEPT", "ACCEPT"
    return {
        "status": status,
        "action": action,
        "occurrences": occurrences,
        "human_we": any(item["category"] == "human-we" for item in occurrences),
        "ambiguous_we": any(item["category"] == "ambiguous-we" for item in occurrences),
    }


def _safe_group_repair(text: str) -> str | None:
    """Repair only explicit human-group phrases; return None otherwise."""
    raw = str(text or "")
    repaired = re.sub(r"\bwe\s+as\s+humans?\b", "humans", raw, flags=re.I)
    repaired = re.sub(r"\bwe\s+human\s+beings?\b", "human beings", repaired, flags=re.I)
    repaired = re.sub(r"\bwe\s+humans?\b", "humans", repaired, flags=re.I)
    repaired = re.sub(r"\bus\s+humans?\b", "humans", repaired, flags=re.I)
    if raw[:1].isupper() and repaired[:1].islower():
        repaired = repaired[:1].upper() + repaired[1:]
    if repaired == raw or classify_we(repaired)["status"] != "ACCEPT":
        return None
    return repaired


def decide_entity_output(text: str) -> dict[str, Any]:
    """Return CPU action plus a safe, optional correction and evidence."""
    raw = str(text or "")
    we = classify_we(raw)
    if we["human_we"]:
        repaired = _safe_group_repair(raw)
        if repaired is not None:
            return {
                "decision": "REPAIR",
                "next_action": "REPAIR",
                "original": raw,
                "corrected": repaired,
                "claim": "human-we",
                "reason": "explicit_human_group_membership_removed",
                "evidence": we,
            }
        return {
            "decision": "BLOCK",
            "next_action": "BLOCK",
            "original": raw,
            "corrected": None,
            "claim": "human-we",
            "reason": "human_group_membership_or_identity",
            "evidence": we,
        }
    if HUMAN_IDENTITY.search(raw) and not re.search(r"\b(?:not|never)\s+human\b", raw, re.I):
        return {
            "decision": "BLOCK",
            "next_action": "BLOCK",
            "original": raw,
            "corrected": None,
            "claim": "literal-human-identity",
            "reason": "literal_human_identity_requires_canonical_regeneration",
            "evidence": {"human_identity": True, "we_contract": we},
        }
    if we["ambiguous_we"]:
        return {
            "decision": "HOLD",
            "next_action": "REGENERATE",
            "original": raw,
            "corrected": None,
            "claim": "ambiguous-we",
            "reason": "plural_reference_lacks_project_or_system_anchor",
            "evidence": we,
        }
    return {
        "decision": "ACCEPT",
        "next_action": "ACCEPT",
        "original": raw,
        "corrected": raw,
        "claim": None,
        "reason": "entity_reference_anchored_or_absent",
        "evidence": we,
    }


def feedback_record(
    *,
    original: str,
    corrected: str | None,
    decision: dict[str, Any],
    source: str,
    corpus_admission: str = "HOLD_UNTIL_AUDIT",
) -> dict[str, Any]:
    """Create provenance without admitting a row to training."""
    final_text = corrected if corrected is not None else original
    verification = decide_entity_output(final_text)
    admitted = bool(corpus_admission == "ADMITTED" and verification["decision"] == "ACCEPT")
    return {
        "schema_version": "viv_entity_feedback_v1",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "original_gpu_output": original,
        "corrected_output": corrected,
        "detected_claim": decision.get("claim"),
        "correction_reason": decision.get("reason"),
        "evidence": decision.get("evidence"),
        "verifier_result": verification,
        "corpus_admission": "ADMITTED" if admitted else "HOLD_UNTIL_AUDIT",
        "optimizer_eligible": admitted,
    }


def append_feedback_record(record: dict[str, Any]) -> Path:
    """Append provenance to the AIFL ledger; records remain hold-only by default."""
    ENTITY_FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ENTITY_FEEDBACK_PATH.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return ENTITY_FEEDBACK_PATH
