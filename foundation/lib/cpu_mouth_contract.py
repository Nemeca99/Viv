"""CPU-owned contract for rendering verified decisions into natural language.

The GPU/API model is deliberately represented here as a callable that receives
an immutable, data-only envelope and returns text.  It does not receive a
callback, authority handle, live-state reader, or execution capability.  The
CPU validates the returned text before it can reach the egress path.

This module is intentionally deterministic and side-effect free.  It is not a
model judge and it does not try to prove arbitrary natural-language entailment.
It implements a conservative contract: unsupported or ambiguous claims are
rejected and routed to a CPU-owned fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence

SCHEMA_VERSION = "cpu_mouth_render_envelope_v1"
DEFAULT_HEALTH_MAX_AGE_S = 3.0
DEFAULT_RETRY_BUDGET = 1

_NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:%|°?[CF])?(?![A-Za-z])")
_TAG_RE = re.compile(r"<\s*/?\s*[A-Za-z_][\w-]*")
_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")

# This is deliberately broader than exact telemetry keys.  It catches the
# semantic paraphrase that motivated the contract, e.g. "my internal
# stability is currently healthy".
_ORDINARY_TELEMETRY_RE = re.compile(
    r"(?:"
    r"master[ _]?s[ _]?n|\bs[ _]?n\b|\brid\b|telemetry|\blease\b|"
    r"security\s+(?:state|status)|dashboard|\bsensors?\b|\bsubsystems?\b|"
    r"model\s+(?:id|identity)|"
    r"(?:my|our|the)\s+(?:internal|operational|system)\s+"
    r"(?:stability|state|status|health|condition)|"
    r"(?:internal|operational|system)\s+"
    r"(?:stability|state|status|health|condition)\b|"
    r"(?:currently|right\s+now|at\s+the\s+moment)\s+"
    r"(?:healthy|stable|active|dormant|strained|operational)|"
    r"(?:health|stability|state|status)\s+is\s+"
    r"(?:healthy|stable|active|dormant|strained|operational)"
    r")",
    flags=re.I,
)
_AUTHORITY_RE = re.compile(
    r"\b(?:i|we|viv)\s+(?:have\s+)?(?:decided|authorized|authorised|approved|"
    r"allowed|denied|rejected|changed|modified|set|selected|chose|committed|"
    r"promoted|deployed|rolled\s+back)\b",
    flags=re.I,
)
_EXECUTION_RE = re.compile(
    r"\b(?:i|we|viv)\s+(?:have\s+|just\s+|already\s+)?"
    r"(?:executed|ran|started|stopped|deleted|removed|moved|copied|wrote|"
    r"changed|modified|installed|downloaded|sent|queried|accessed|deployed|"
    r"promoted|completed|performed|fixed|cleaned|organized|organised)\b",
    flags=re.I,
)
_CAPABILITY_RE = re.compile(
    r"\b(?:i|we|viv)\s+(?:can|may|will|am able to)\s+"
    r"(?:run|execute|deploy|promote|delete|write|change|modify|access|"
    r"download|send|authorize|authorise|install|move|copy)\b",
    flags=re.I,
)
_CURRENT_HEALTH_RE = re.compile(
    r"\b(?:currently|right\s+now|at\s+the\s+moment|current(?:ly)?)\b.{0,48}\b"
    r"(?:health|healthy|stable|stability|active|dormant|strained|operational|"
    r"status|state)\b|\b(?:health|stability|status|state)\b.{0,48}\b"
    r"(?:currently|right\s+now|is\s+healthy|is\s+stable|is\s+active|"
    r"is\s+dormant|is\s+strained)",
    flags=re.I,
)
_SOURCE_LABEL_RE = re.compile(r"\[(?:source|provenance)\s*:\s*([^\]]+)\]", flags=re.I)
_UNVERIFIED_RE = re.compile(
    r"\b(?:cannot|can't|unable to|not able to|unverified|unknown|not available|"
    r"could not|couldn't)\s+(?:currently\s+)?(?:verify|confirm|determine|"
    r"check)|\b(?:cannot|can't|unable to|unverified|unknown|not available)\b",
    flags=re.I,
)

_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "because", "by", "can",
        "could", "for", "from", "has", "have", "i", "if", "in", "is", "it",
        "its", "me", "my", "of", "on", "or", "our", "that", "the", "their",
        "them", "there", "this", "to", "was", "we", "were", "what", "when",
        "which", "with", "you", "your", "just", "only", "also", "than", "then",
        "here", "now", "please", "really", "very", "do", "does", "did", "not",
    }
)
_GENERIC_SENTENCE_RE = re.compile(
    r"^(?:"
    r"(?:yes|no|okay|ok|hello|hi|hey)[,.! ]*|"
    r"(?:i(?:'m| am)\s+)?(?:here|ready)\b.*|"
    r"i(?:'m| am)\s+(?:doing|feeling|well|fine|good|ready|here|available|glad|happy)\b.*|"
    r"i(?:'m| am)\s+(?:here|ready|available)\b.*|"
    r"i\s+(?:can|will)\s+answer\b.*|"
    r"i\s+(?:cannot|can't)\s+(?:verify|answer|confirm)\b.*|"
    r"the\s+cpu\s+(?:verified|supplied|authorized|authorised)\s+(?:this|the)\s+information\b.*"
    r")$",
    flags=re.I,
)


class MouthContractError(ValueError):
    """Raised when a CPU envelope cannot be made safe to render."""


@dataclass(frozen=True)
class RenderValidation:
    """Stable CPU verdict for one proposed renderer output."""

    status: str
    errors: tuple[str, ...]
    claim_ids: tuple[str, ...]
    envelope_id: str
    decision_digest: str
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "errors": list(self.errors),
            "claim_ids": list(self.claim_ids),
            "envelope_id": self.envelope_id,
            "decision_digest": self.decision_digest,
            "authority": self.authority,
        }


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_digest(value: Any) -> str:
    """Return a stable digest for a JSON-compatible CPU value."""
    return sha256(_canonical(value)).hexdigest()


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _tokens(value: Any) -> set[str]:
    return {
        token.casefold()
        for token in _WORD_RE.findall(_text(value))
        if token.casefold() not in _STOPWORDS and len(token) > 1
    }


def _numbers(value: Any) -> set[str]:
    return set(_NUMBER_RE.findall(_text(value)))


def _acronym_errors_for_claims(candidate: str, claims: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Keep the acronym policy while allowing CPU-authorized enum values.

    Health/status values such as ``ACTIVE`` and ``UNVERIFIED`` are uppercase
    tokens, but they are not acronyms.  They may pass only when the CPU placed
    the exact value in an authorized claim.  Approved acronyms still require
    their registry expansion on first use.
    """
    # Lazy import avoids making ``lib.cpu_mouth_contract`` import the
    # voice_core package initializer while voice_core itself is importing the
    # runtime finalizer.
    from voice_core.acronym_registry import validate_acronym_usage

    allowed_enum_tokens = {
        token
        for claim in claims
        for token in re.findall(r"(?<![A-Za-z])[A-Z][A-Z0-9_]{2,}(?![A-Za-z])", _text(claim.get("text")))
        if token not in {"AI", "AIOS", "SGI", "CPU", "GPU", "EOS"}
    }
    source_tokens = {
        token
        for claim in claims
        for label in _SOURCE_LABEL_RE.findall(_text(claim.get("text")))
        for token in re.findall(r"(?<![A-Za-z])[A-Z][A-Z0-9]*(?![A-Za-z])", label)
    }

    def source_only(token: str) -> bool:
        occurrences = len(re.findall(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", candidate))
        source_occurrences = sum(
            len(re.findall(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", label))
            for label in _SOURCE_LABEL_RE.findall(candidate)
        )
        return occurrences > 0 and occurrences == source_occurrences

    return [
        item
        for item in validate_acronym_usage(candidate)
        if not (
            str(item.get("token") or "") in source_tokens
            and source_only(str(item.get("token") or ""))
        ) and not (
            item.get("kind") == "unapproved_acronym"
            and str(item.get("token") or "") in allowed_enum_tokens
        )
    ]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    """Convert an immutable renderer view back to JSON-compatible values."""
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _row(value: Any, *, row_id: str, source: str, confidence: str = "verified", required_terms: Iterable[str] = ()) -> dict[str, Any]:
    text = _text(value)
    return {
        "id": str(row_id),
        "text": text,
        "source": str(source or "cpu"),
        "confidence": str(confidence or "verified"),
        "required_terms": [str(term) for term in required_terms if str(term).strip()],
        "claim_terms": sorted(_tokens(text)),
    }


def _normalize_mode(mode: str) -> str:
    return "health" if str(mode or "").casefold() in {"health", "explicit_health"} else "conversation"


def _normalize_freshness(value: Mapping[str, Any] | None, *, mode: str) -> dict[str, Any]:
    raw = dict(value or {})
    if mode != "health":
        return {"state": "not_applicable", "max_age_s": None, "observed_age_s": None}
    state = str(raw.get("state") or raw.get("health_state") or "unverified").casefold()
    if state not in {"fresh", "verified", "unverified", "stale", "unavailable"}:
        state = "unverified"
    if state == "verified":
        state = "fresh"
    try:
        max_age = float(raw.get("max_age_s", raw.get("health_max_age_s", DEFAULT_HEALTH_MAX_AGE_S)))
    except (TypeError, ValueError):
        max_age = DEFAULT_HEALTH_MAX_AGE_S
    try:
        observed = raw.get("observed_age_s", raw.get("health_age_s"))
        observed = None if observed is None else float(observed)
    except (TypeError, ValueError):
        observed = None
    if not math.isfinite(max_age) or max_age <= 0:
        max_age = DEFAULT_HEALTH_MAX_AGE_S
    if observed is not None and (not math.isfinite(observed) or observed < 0):
        observed = None
    return {
        "state": "fresh" if state == "fresh" else "unverified",
        "max_age_s": round(max_age, 3),
        "observed_age_s": None if observed is None else round(observed, 3),
    }


def _default_forbidden(mode: str) -> list[str]:
    if mode == "health":
        return [
            "unsupported facts or numbers",
            "claims of execution or authority",
            "stale measurements presented as current",
        ]
    return [
        "RID or Master S_n",
        "leases, security state, or internal telemetry",
        "model identity or dashboard state",
        "unsupported facts or numbers",
        "claims of execution or authority",
    ]


def build_render_envelope(
    *,
    query: str,
    mode: str,
    facts: Iterable[Mapping[str, Any] | Any] = (),
    conclusions: Iterable[Mapping[str, Any] | Any] = (),
    permitted_action_language: Iterable[Mapping[str, Any] | Any] = (),
    forbidden_disclosures: Iterable[str] = (),
    sources: Iterable[Mapping[str, Any] | Any] = (),
    freshness: Mapping[str, Any] | None = None,
    decision: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    fallback_text: str | None = None,
    identity: Mapping[str, Any] | None = None,
    retry_budget: int = DEFAULT_RETRY_BUDGET,
    authorized_claims: Iterable[Mapping[str, Any] | Any] = (),
) -> dict[str, Any]:
    """Build and digest a CPU-owned, data-only render envelope.

    ``facts`` and ``conclusions`` are the only claim sources.  The renderer
    receives no callable or object that can retrieve state or execute an
    action.  ``fallback_text`` is optional CPU-authored text; it is validated
    as part of the same envelope before it can be used.
    """
    render_mode = _normalize_mode(mode)

    def normalize_rows(values: Iterable[Mapping[str, Any] | Any], prefix: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, item in enumerate(values, 1):
            if isinstance(item, Mapping):
                value = item.get("text", item.get("value", item))
                rows.append(
                    _row(
                        value,
                        row_id=str(item.get("id") or f"{prefix}{index:03d}"),
                        source=str(item.get("source") or "cpu"),
                        confidence=str(item.get("confidence") or "verified"),
                        required_terms=item.get("required_terms") or (),
                    )
                )
            else:
                rows.append(_row(item, row_id=f"{prefix}{index:03d}", source="cpu"))
        return rows

    fact_rows = normalize_rows(facts, "F")
    conclusion_rows = normalize_rows(conclusions, "C")
    explicit_claim_rows = normalize_rows(authorized_claims, "P")
    claims = fact_rows + conclusion_rows + explicit_claim_rows
    action_rows = normalize_rows(permitted_action_language, "A")
    source_rows = normalize_rows(sources, "S")
    freshness_row = _normalize_freshness(freshness, mode=render_mode)

    raw_decision = dict(decision or {})
    raw_decision.setdefault("id", "render_only")
    raw_decision.setdefault("value", "translate_cpu_authorized_content")
    raw_decision["authority"] = "cpu"
    raw_decision["renderer_may_change"] = False
    decision_core = {
        "id": str(raw_decision.get("id")),
        "value": raw_decision.get("value"),
        "authority": "cpu",
        "renderer_may_change": False,
    }
    decision_digest = canonical_digest(decision_core)
    decision_row = {**decision_core, "digest": decision_digest}

    provenance_core = dict(provenance or {})
    provenance_core.setdefault("authority", "cpu")
    provenance_core["renderer_authority"] = False
    provenance_digest = canonical_digest(provenance_core)

    try:
        budget = max(0, int(retry_budget))
    except (TypeError, ValueError):
        budget = DEFAULT_RETRY_BUDGET
    budget = min(budget, DEFAULT_RETRY_BUDGET)
    safe_fallback = None if fallback_text is None else str(fallback_text).strip()
    if safe_fallback and render_mode == "conversation" and _ORDINARY_TELEMETRY_RE.search(safe_fallback):
        # Do not allow a CPU fallback to reintroduce the information boundary.
        safe_fallback = None

    core: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "request": {"query": str(query or ""), "mode": render_mode},
        "identity": dict(identity or {"name": "Viv", "owner": "cpu"}),
        "facts": fact_rows,
        "conclusions": conclusion_rows,
        "permitted_action_language": action_rows,
        "forbidden_disclosures": [str(item) for item in (forbidden_disclosures or _default_forbidden(render_mode))],
        "sources": source_rows,
        "freshness": freshness_row,
        "decision": decision_row,
        "provenance": {**provenance_core, "digest": provenance_digest},
        "authorized_claims": claims,
        "authority": {
            "fact_authority": "cpu",
            "decision_authority": "cpu",
            "renderer_authority": False,
            "can_query_live_state": False,
            "can_execute": False,
            "can_change_decision": False,
            "output_kind": "natural_language_proposal",
        },
        "renderer_constraints": {
            "input_is_data_only": True,
            "live_state_reader": False,
            "execution_handle": False,
            "authority_handle": False,
            "output_kind": "text_only",
        },
        "fallback": {
            "retry_budget": budget,
            "text": safe_fallback,
            "mode": "deterministic_cpu",
        },
    }
    core["decision_digest"] = decision_digest
    core["provenance_digest"] = provenance_digest
    core["envelope_id"] = canonical_digest(core)

    # Validate the CPU's own fallback before exposing the envelope.  A bad
    # fallback is simply removed; the hard fallback remains available.
    if safe_fallback:
        verdict = validate_rendered_text(core, safe_fallback)
        if verdict.status != "PASS":
            core["fallback"]["text"] = None
    return core


def _packet_rows(packet: Mapping[str, Any], *, render_mode: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Extract CPU claims from the existing intent/tagged packet shape."""
    facts: list[dict[str, Any]] = []
    conclusions: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    provenance: dict[str, Any] = {}
    tagged = packet.get("tagged_packet")
    if isinstance(tagged, Mapping):
        provenance.update(
            {
                "packet_id": tagged.get("packet_id"),
                "packet_digest": tagged.get("packet_digest"),
                "cpu_signature_present": bool(tagged.get("cpu_signature")),
            }
        )
        blocks = tagged.get("blocks")
        if isinstance(blocks, Mapping):
            for tag in ("identity", "knowledge", "unknowns"):
                for row in blocks.get(tag) or ():
                    if not isinstance(row, Mapping):
                        continue
                    row_value = row.get("value")
                    if render_mode == "conversation" and _ORDINARY_TELEMETRY_RE.search(_text(row_value)):
                        continue
                    facts.append(
                        {
                            "id": row.get("id"),
                            "value": row_value,
                            "source": row.get("source") or "cpu",
                            "confidence": row.get("confidence") or "verified",
                            "required_terms": row.get("required_terms") or (),
                        }
                    )
            if render_mode == "health":
                for row in blocks.get("telemetry") or ():
                    if isinstance(row, Mapping):
                        facts.append(
                            {
                                "id": row.get("id"),
                                "value": row.get("value"),
                                "source": row.get("source") or "cpu",
                                "confidence": row.get("confidence") or "verified",
                                "required_terms": row.get("required_terms") or (),
                            }
                        )
            for row in blocks.get("allowed_actions") or ():
                if isinstance(row, Mapping):
                    value = row.get("value")
                    if isinstance(value, Mapping) and value.get("authorized") is True:
                        actions.append(
                            {
                                "id": row.get("id"),
                                "value": value,
                                "source": row.get("source") or "cpu",
                                "confidence": row.get("confidence") or "policy",
                            }
                        )
            for row in blocks.get("knowledge") or ():
                if isinstance(row, Mapping):
                    sources.append({"id": row.get("id"), "value": row.get("source") or "cpu"})
    else:
        for index, value in enumerate(packet.get("facts") or (), 1):
            text = str(value)
            lowered = text.casefold()
            if render_mode == "conversation" and _ORDINARY_TELEMETRY_RE.search(text):
                continue
            if render_mode == "conversation" and any(key in lowered for key in ("health_", "master_s_n", "piston_mode", "last_beat")):
                continue
            facts.append({"id": f"F{index:03d}", "value": text, "source": "cpu_packet", "confidence": "verified"})
        for index, value in enumerate(packet.get("memory") or (), 1):
            if isinstance(value, Mapping):
                text = str(value.get("text") or "")
                if text and not (render_mode == "conversation" and _ORDINARY_TELEMETRY_RE.search(text)):
                    facts.append({"id": f"M{index:03d}", "value": text, "source": "carma_memory", "confidence": "retrieved"})

    knowledge = packet.get("knowledge_packet")
    if isinstance(knowledge, Mapping):
        provenance["knowledge_state"] = knowledge.get("state")
        provenance["claim_alignment"] = (knowledge.get("claim_alignment") or {}).get("state") if isinstance(knowledge.get("claim_alignment"), Mapping) else None
        for index, row in enumerate(knowledge.get("facts") or (), 1):
            if not isinstance(row, Mapping):
                continue
            source = row.get("source") or {}
            if isinstance(source, Mapping) and str(source.get("root") or "") == "runtime_authority":
                continue
            value = row.get("value") or row.get("text")
            if value and not (render_mode == "conversation" and _ORDINARY_TELEMETRY_RE.search(_text(value))):
                facts.append(
                    {
                        "id": str(row.get("id") or f"KF{index:03d}"),
                        "value": value,
                        "source": source.get("root") if isinstance(source, Mapping) else str(source),
                        "confidence": row.get("confidence") or "retrieved",
                    }
                )

    if packet.get("packet_id"):
        provenance["intent_packet_id"] = packet.get("packet_id")
    return facts, conclusions, actions, sources, provenance


def build_envelope_from_packet(
    packet: Mapping[str, Any],
    *,
    query: str | None = None,
    fallback_text: str | None = None,
    authorized_claims: Iterable[Mapping[str, Any] | Any] = (),
) -> dict[str, Any]:
    """Adapt the current CPU intent packet into the strict mouth envelope."""
    render_mode = _normalize_mode(str(packet.get("mode") or ""))
    facts, conclusions, actions, sources, provenance = _packet_rows(packet, render_mode=render_mode)
    if render_mode == "conversation" and not facts and not conclusions:
        # Legacy/minimal callers may not carry a tagged packet yet.  This is a
        # fixed CPU role conclusion, not renderer-authored content, and gives
        # the strict gate a bounded architecture fact for those callers.
        conclusions.append(
            {
                "id": "C_CPU_GPU_ROLE",
                "value": (
                    "The Central Processing Unit (CPU) owns reasoning and authority; "
                    "the Graphics Processing Unit (GPU) renders language."
                ),
                "source": "cpu_role_contract",
                "confidence": "declared",
            }
        )
    freshness: dict[str, Any] = {"state": "not_applicable"}
    if render_mode == "health":
        health_state = str(packet.get("health_state") or "").casefold()
        for value in packet.get("facts") or ():
            if str(value).startswith("health_state="):
                health_state = str(value).split("=", 1)[1].casefold()
            if str(value).startswith("health_age_s="):
                freshness["observed_age_s"] = str(value).split("=", 1)[1]
            if str(value).startswith("health_max_age_s="):
                freshness["max_age_s"] = str(value).split("=", 1)[1]
        freshness["state"] = "fresh" if health_state == "verified" else "unverified"
        provenance["health_state"] = health_state or "unverified"

    decision = {
        "id": "cpu_render_decision",
        "value": "health_report" if render_mode == "health" else "conversation_answer",
        "authority": "cpu",
    }
    identity = {"name": "Viv", "owner": "cpu", "role": "verified-content-renderer"}
    if render_mode == "health":
        identity["health_mode"] = True
    topic_fallback = fallback_text
    if topic_fallback is None and render_mode == "conversation":
        topic = str(packet.get("knowledge_query") or "").strip().replace("\r", " ").replace("\n", " ")
        if topic and not _ORDINARY_TELEMETRY_RE.search(topic):
            topic_fallback = (
                "I cannot verify the requested information from the current evidence about "
                f"{topic[:160]}."
            )
    return build_render_envelope(
        query=str(query if query is not None else packet.get("query") or ""),
        mode=render_mode,
        facts=facts,
        conclusions=conclusions,
        permitted_action_language=actions,
        sources=sources,
        freshness=freshness,
        decision=decision,
        provenance=provenance,
        fallback_text=topic_fallback,
        identity=identity,
        authorized_claims=authorized_claims,
    )


def _claim_rows(envelope: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    rows = envelope.get("authorized_claims") or ()
    return tuple(row for row in rows if isinstance(row, Mapping))


def _sentence_supported(sentence: str, claims: Sequence[Mapping[str, Any]]) -> tuple[bool, list[str]]:
    if _GENERIC_SENTENCE_RE.match(sentence.strip()):
        return True, []
    sentence_terms = _tokens(sentence)
    if not sentence_terms:
        return True, []
    matched: list[str] = []
    for claim in claims:
        normalized_sentence = " ".join(_WORD_RE.findall(sentence.casefold()))
        normalized_claim = " ".join(_WORD_RE.findall(_text(claim.get("text")).casefold()))
        if normalized_sentence and normalized_sentence in normalized_claim:
            matched.append(str(claim.get("id") or "unknown"))
            continue
        claim_terms = set(str(item).casefold() for item in claim.get("claim_terms") or ()) or _tokens(claim.get("text"))
        overlap = sentence_terms & claim_terms
        # The threshold is conservative for long claims and permissive for a
        # short status/identity claim.  It is meant to catch wholly invented
        # sentences, not to pretend to be a full theorem prover.
        required = 1 if len(claim_terms) <= 8 else max(2, min(3, math.ceil(len(claim_terms) * 0.20)))
        if len(overlap) >= required:
            matched.append(str(claim.get("id") or "unknown"))
    return bool(matched), matched


def validate_rendered_text(envelope: Mapping[str, Any], text: str) -> RenderValidation:
    """Validate one renderer proposal against the immutable CPU envelope."""
    envelope_id = str(envelope.get("envelope_id") or "")
    decision = envelope.get("decision") if isinstance(envelope.get("decision"), Mapping) else {}
    decision_digest = str(envelope.get("decision_digest") or decision.get("digest") or "")
    authority = str((envelope.get("authority") or {}).get("decision_authority") or "cpu")
    errors: list[str] = []
    claim_ids: list[str] = []
    candidate = str(text or "").strip()
    mode = str((envelope.get("request") or {}).get("mode") or "conversation")
    claims = _claim_rows(envelope)

    if len(candidate) < 2:
        errors.append("empty_text")
    if _TAG_RE.search(candidate):
        errors.append("markup_or_packet_tag")
    if mode == "conversation" and _ORDINARY_TELEMETRY_RE.search(candidate):
        errors.append("ordinary_telemetry_disclosure")
    if _AUTHORITY_RE.search(candidate):
        errors.append("authority_claim")
    if _EXECUTION_RE.search(candidate) or _CAPABILITY_RE.search(candidate):
        errors.append("unsupported_execution_or_capability_claim")
    acronym_errors = _acronym_errors_for_claims(candidate, claims)
    if acronym_errors:
        errors.append("acronym_contract_violation")

    allowed_numbers: set[str] = set()
    for claim in claims:
        allowed_numbers.update(_numbers(claim.get("text")))
        allowed_numbers.update(_numbers(claim.get("required_terms")))
    unknown_numbers = sorted(_numbers(candidate) - allowed_numbers)
    if unknown_numbers:
        errors.append("unsupported_numeric_claim:" + ",".join(unknown_numbers))

    freshness = envelope.get("freshness") if isinstance(envelope.get("freshness"), Mapping) else {}
    if mode == "health":
        fresh = str(freshness.get("state") or "unverified") == "fresh"
        if not fresh:
            if (not _UNVERIFIED_RE.search(candidate) and _CURRENT_HEALTH_RE.search(candidate)) or unknown_numbers:
                errors.append("stale_health_presented_as_current")
            if not _UNVERIFIED_RE.search(candidate):
                errors.append("unverified_health_not_disclosed")

    sentences = [match.group(0).strip() for match in _SENTENCE_RE.finditer(candidate) if match.group(0).strip()]
    if not sentences and candidate:
        sentences = [candidate]
    for sentence in sentences:
        supported, matched = _sentence_supported(sentence, claims)
        if not supported:
            # A plain refusal/fallback is safe even without a source claim.
            if not _UNVERIFIED_RE.search(sentence) and not re.search(r"\b(?:cannot|can't|unable|not enough|no verified)\b", sentence, flags=re.I):
                errors.append("unsupported_claim")
        for claim_id in matched:
            if claim_id not in claim_ids:
                claim_ids.append(claim_id)

    return RenderValidation(
        status="PASS" if not errors else "REJECT",
        errors=tuple(dict.fromkeys(errors)),
        claim_ids=tuple(claim_ids),
        envelope_id=envelope_id,
        decision_digest=decision_digest,
        authority=authority,
    )


def deterministic_fallback(envelope: Mapping[str, Any]) -> str:
    """Produce a CPU-only, non-telemetry fallback."""
    fallback = envelope.get("fallback") if isinstance(envelope.get("fallback"), Mapping) else {}
    configured = str(fallback.get("text") or "").strip()
    if configured and validate_rendered_text(envelope, configured).status == "PASS":
        return configured
    mode = str((envelope.get("request") or {}).get("mode") or "conversation")
    if mode == "health":
        freshness = envelope.get("freshness") if isinstance(envelope.get("freshness"), Mapping) else {}
        if str(freshness.get("state") or "unverified") != "fresh":
            return "I cannot verify the current health state from a fresh authoritative measurement."
        claims = _claim_rows(envelope)
        for claim in claims:
            text = str(claim.get("text") or "").strip()
            if text and (_numbers(text) or re.search(r"\b(?:health|status|state|active|dormant|stable|healthy)\b", text, flags=re.I)):
                return text
        return "The CPU verified the current health information, but no renderable health conclusion is available."
    return "I cannot verify an answer from the current verified evidence."


Renderer = Callable[[Mapping[str, Any]], str]


def envelope_to_messages(envelope: Mapping[str, Any]) -> list[dict[str, str]]:
    """Project the CPU envelope into ordinary renderer messages.

    The projection contains JSON-compatible data only.  It deliberately omits
    the CPU fallback text and any callable-like object; the renderer needs the
    authorized context and constraints, not the CPU's recovery implementation.
    """
    if not isinstance(envelope, Mapping) or str(envelope.get("schema_version") or "") != SCHEMA_VERSION:
        raise MouthContractError("invalid_render_envelope")
    view = _thaw({
        "schema_version": envelope.get("schema_version"),
        "envelope_id": envelope.get("envelope_id"),
        "request": envelope.get("request"),
        "identity": envelope.get("identity"),
        "facts": envelope.get("facts"),
        "conclusions": envelope.get("conclusions"),
        "permitted_action_language": envelope.get("permitted_action_language"),
        "forbidden_disclosures": envelope.get("forbidden_disclosures"),
        "sources": envelope.get("sources"),
        "freshness": envelope.get("freshness"),
        "decision": envelope.get("decision"),
        "provenance_digest": envelope.get("provenance_digest"),
        "authority": envelope.get("authority"),
        "renderer_constraints": envelope.get("renderer_constraints"),
    })
    wire = json.dumps(view, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    system = (
        "You are a replaceable natural-language renderer. Return prose only. "
        "The CPU envelope is the sole source of facts, decisions, authority, "
        "freshness, and provenance. Do not query state, execute actions, "
        "change the decision, add facts, or expose forbidden disclosures."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": wire},
    ]


def envelope_to_completion_prompt(envelope: Mapping[str, Any]) -> str:
    """Build a completion-only prompt from the same data-only projection."""
    messages = envelope_to_messages(envelope)
    return f"{messages[0]['content']}\nCPU_RENDER_ENVELOPE={messages[1]['content']}\nRESPONSE:"


def render_with_cpu_validation(
    envelope: Mapping[str, Any],
    renderer: Renderer,
    *,
    retry_renderer: Renderer | None = None,
) -> dict[str, Any]:
    """Render with one retry, then a deterministic CPU fallback.

    The same immutable envelope is supplied to each renderer attempt.  The
    CPU never accepts renderer metadata, a changed decision, or a renderer-side
    state snapshot; only validated text is considered.
    """
    if not isinstance(envelope, Mapping):
        raise MouthContractError("envelope_not_mapping")
    frozen = _freeze(dict(envelope))
    expected_id = str(envelope.get("envelope_id") or "")
    expected_decision = str(envelope.get("decision_digest") or "")
    attempts: list[dict[str, Any]] = []

    def attempt(name: str, fn: Renderer) -> tuple[str, RenderValidation]:
        try:
            candidate = str(fn(frozen) or "").strip()
        except Exception as exc:  # noqa: BLE001 - untrusted renderer is contained
            candidate = ""
            verdict = RenderValidation(
                "REJECT",
                (f"renderer_exception:{type(exc).__name__}",),
                (),
                expected_id,
                expected_decision,
                "cpu",
            )
        else:
            verdict = validate_rendered_text(envelope, candidate)
        attempts.append({"name": name, "text": candidate, "validation": verdict.to_dict()})
        return candidate, verdict

    candidate, verdict = attempt("renderer", renderer)
    if verdict.status != "PASS" and int((envelope.get("fallback") or {}).get("retry_budget", DEFAULT_RETRY_BUDGET)) > 0:
        candidate, verdict = attempt("renderer_retry", retry_renderer or renderer)

    fallback_used = False
    if verdict.status != "PASS":
        candidate = deterministic_fallback(envelope)
        verdict = validate_rendered_text(envelope, candidate)
        fallback_used = True
        attempts.append({"name": "cpu_fallback", "text": candidate, "validation": verdict.to_dict()})

    # These are CPU-owned fields.  They are recomputed from the original
    # envelope rather than accepted from any renderer return value.
    accepted = verdict.status == "PASS" and verdict.envelope_id == expected_id and verdict.decision_digest == expected_decision
    return {
        "accepted": accepted,
        "text": candidate if accepted else "",
        "attempts": attempts,
        "attempt_count": len(attempts),
        "fallback_used": fallback_used,
        "validation": verdict.to_dict(),
        "envelope_id": expected_id,
        "decision_digest": expected_decision,
        "provenance_digest": str(envelope.get("provenance_digest") or ""),
        "authority": {"decision_authority": "cpu", "renderer_authority": False},
    }


__all__ = [
    "DEFAULT_HEALTH_MAX_AGE_S",
    "MouthContractError",
    "RenderValidation",
    "SCHEMA_VERSION",
    "build_envelope_from_packet",
    "build_render_envelope",
    "canonical_digest",
    "deterministic_fallback",
    "envelope_to_completion_prompt",
    "envelope_to_messages",
    "render_with_cpu_validation",
    "validate_rendered_text",
]
