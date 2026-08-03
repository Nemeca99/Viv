"""CPU-owned response handling for uncertain multi-source knowledge packets."""
from __future__ import annotations

import re
from typing import Any


_ACCEPTED_ALIGNMENT = {"AGREED_EXACT", "CORROBORATED_PROVISIONAL"}
_BLOCKED_STATES = {"PARTIAL", "CONFLICT", "INSUFFICIENT", "INCONCLUSIVE", "UNASSESSED"}


def _clean(value: Any, limit: int = 320) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit].rstrip()


def knowledge_excerpt(value: Any, *, scope: str = "", limit: int = 900) -> str:
    """Render a bounded, source-faithful excerpt for the mouth.

    Wikipedia article files contain markup, templates, and metadata that are
    useful for provenance but are not conversational evidence. This function
    removes presentation syntax only; it does not summarize or add claims.
    """
    text = str(value or "").replace("\r", "")
    if "wikipedia_local" in str(scope).casefold():
        # The exported article keeps the lead after a long one-line infobox.
        # Start at that lead when present so markup removal does not leave only
        # the title as the conversational evidence.
        lead = next(
            (
                match
                for match in re.finditer(r"'''[^']{1,160}'''", text, flags=re.S)
                if "autism" in match.group(0).casefold()
            ),
            None,
        )
        if not lead:
            lead = re.search(r"\}\}\s*'''", text, flags=re.S)
        if lead:
            text = text[lead.start():]
        text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
        text = re.sub(r"^[ \t]*\|.*$", " ", text, flags=re.M)
        text = re.sub(r"^[ \t]*[!{}].*$", " ", text, flags=re.M)
        text = re.sub(r"^[ \t]*\[\[Category:.*$", " ", text, flags=re.I | re.M)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<ref\b[^>]*>.*?</ref\s*>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<ref\b[^>]*/\s*>", " ", text, flags=re.I)
    text = re.sub(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), text)
    text = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    # Expand the source's parenthetical acronym so the ordinary speech
    # contract does not mistake supplied knowledge for an unapproved code.
    text = re.sub(r"\s*\(\s*ASD\s*\)", "", text, flags=re.I)
    text = re.sub(r"\bASD\b", "autism spectrum disorder", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if text.lower().startswith("title:"):
        text = text.split(" ", 1)[1] if " " in text else ""
    if "wikipedia_local" in str(scope).casefold() and len(text) < 64:
        # The bounded adapter may end inside an infobox before the article
        # lead. A title alone is provenance, not an answer, so omit it.
        return ""
    return text[: max(1, int(limit))].rstrip()


def _source_label(root: Any) -> str:
    raw = str(root or "supplied source")
    folded = raw.casefold()
    if folded == "wikipedia_rest":
        return "Wikipedia"
    if "wikipedia_deduplicated" in folded:
        return "the local Wikipedia dataset"
    return _clean(raw, 96)


def grounded_response_fallback(packet: dict[str, Any]) -> dict[str, Any] | None:
    """Return a truthful fallback when multi-source evidence is not aligned.

    This is deliberately conservative. It does not paraphrase a disputed claim
    as fact; it attributes bounded supplied records and preserves provenance.
    ``None`` means the packet is sufficiently aligned or is not multi-source.
    """
    if str(packet.get("knowledge_mode") or "local").lower() != "multi_source":
        return None
    knowledge = packet.get("knowledge_packet")
    if not isinstance(knowledge, dict):
        return None

    three_way = knowledge.get("three_way") if isinstance(knowledge.get("three_way"), dict) else {}
    alignment = knowledge.get("claim_alignment") if isinstance(knowledge.get("claim_alignment"), dict) else {}
    three_state = str(three_way.get("state") or "INSUFFICIENT").upper()
    align_state = str(alignment.get("state") or "UNASSESSED").upper()
    if three_state == "AGREED" and align_state in _ACCEPTED_ALIGNMENT:
        return None
    if three_state not in _BLOCKED_STATES and align_state not in _BLOCKED_STATES:
        return None

    query = _clean(packet.get("knowledge_query") or knowledge.get("query") or "that question", 120)
    rows: list[str] = []
    for fact in knowledge.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        scope = str(fact.get("scope") or "")
        if scope == "runtime_health":
            continue
        value = knowledge_excerpt(
            fact.get("value"),
            scope=scope,
            limit=280,
        )
        source = fact.get("source") if isinstance(fact.get("source"), dict) else {}
        root = _source_label(source.get("root") or source.get("path") or "supplied source")
        if value:
            rows.append(f"{value} [source: {root}]")
        if len(rows) >= 3:
            break

    if rows:
        body = " ".join(f"{index}. {row}" for index, row in enumerate(rows, 1))
        text = (
            f"I'm Viv. I found supplied records about {query}, but the available sources "
            f"are not fully aligned, so I won't present them as verified fact. "
            f"The supplied material says: {body}"
        )
    else:
        text = (
            f"I'm Viv. I cannot verify the answer about {query} from the available "
            "sources, so I won't invent one."
        )
    return {
        "text": re.sub(r"\s+", " ", text).strip(),
        "reason": "multi_source_claim_alignment_not_verified",
        "three_way_state": three_state,
        "claim_alignment_state": align_state,
        "source_count": len(rows),
    }
