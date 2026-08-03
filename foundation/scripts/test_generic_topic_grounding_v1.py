"""Read-only regression for multi-source disagreement and answer grounding."""
from __future__ import annotations

from unittest.mock import patch

from lib.knowledge_external_adapters import wikipedia_fact_from_payload
from voice_core.intent_packet import build_intent_packet, contains_telemetry_disclosure
from voice_core.knowledge_grounding import grounded_response_fallback
from voice_core.runtime_contract import finalize_draft


TOPICS = (
    ("What is evolution?", "evolution", "Evolution", "Evolution is change in heritable characteristics across generations."),
    ("What is photosynthesis?", "photosynthesis", "Photosynthesis", "Photosynthesis converts light energy into chemical energy in plants."),
    ("Who was Albert Einstein?", "Albert Einstein", "Albert Einstein", "Albert Einstein was a German-born theoretical physicist."),
)


def _rest_result(title: str, extract: str) -> dict:
    fact = wikipedia_fact_from_payload(title, {"extract": extract})
    return {"ok": True, "state": "VERIFIED", "fact": fact.to_dict(), "source": fact.source.to_dict()}


def main() -> int:
    # Keep the test deterministic while exercising the real local corpus and
    # the real CPU packet/alignment/grounding path.
    def fake_rest(title: str, *, timeout_s: float = 5.0) -> dict:
        for _query, _knowledge_query, expected_title, extract in TOPICS:
            if title.casefold() == expected_title.casefold():
                return _rest_result(expected_title, extract)
        return {"ok": False, "state": "INCONCLUSIVE", "error": "test_title_missing"}

    for query, knowledge_query, title, _extract in TOPICS:
        with patch("lib.knowledge_external_adapters.fetch_wikipedia_summary", side_effect=fake_rest):
            packet = build_intent_packet(
                query=query,
                knowledge_query=knowledge_query,
                knowledge_mode="multi_source",
                wikipedia_title=title,
                include_legacy_wikipedia=True,
                resolve_legacy_redirects=True,
                mode="converse",
            )
        knowledge = packet.get("knowledge_packet") or {}
        three_way = (knowledge.get("three_way") or {}).get("state")
        alignment = (knowledge.get("claim_alignment") or {}).get("state")
        fallback = grounded_response_fallback(packet)
        if not fallback or fallback.get("reason") != "multi_source_claim_alignment_not_verified":
            raise AssertionError(f"grounding_missing:{title}:{three_way}:{alignment}")
        text = str(fallback.get("text") or "")
        if "not fully aligned" not in text or "[source:" not in text:
            raise AssertionError(f"uncertainty_or_source_missing:{title}:{text}")
        finalized = finalize_draft(
            query=query,
            packet=packet,
            raw_text="The supplied evidence is enough for me to state this as certain.",
            voice_source="generic_topic_grounding_regression",
        )
        final_text = str(finalized.get("text") or "")
        if "not fully aligned" not in final_text or "[source:" not in final_text:
            raise AssertionError(f"finalizer_dropped_grounding:{title}:{final_text}")
        if contains_telemetry_disclosure(final_text):
            raise AssertionError(f"grounding_leaked_telemetry:{title}")
        print(f"PASS {title}: three_way={three_way} alignment={alignment} grounded=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
