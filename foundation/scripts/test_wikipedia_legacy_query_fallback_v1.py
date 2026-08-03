"""Regression tests for natural-language Wikipedia fallback routing."""
from __future__ import annotations

from lib.knowledge_external_adapters import compose_multi_source_packet, query_legacy_wikipedia
from voice_core.intent_packet import build_intent_packet, contains_telemetry_disclosure, packet_to_messages


def main() -> int:
    cases = (
        ("What is autism?", "Autism"),
        ("What causes autism?", "Causes of autism"),
        ("photosynthesis", "Photosynthesis"),
        ("Albert Einstein", "Albert Einstein"),
    )
    for query, expected_title in cases:
        result = query_legacy_wikipedia(query, limit=3, max_chars=300, resolve_redirects=True)
        paths = [str((row.get("source") or {}).get("path") or "") for row in result.get("facts") or []]
        if result.get("state") != "VERIFIED":
            raise AssertionError(f"query_not_verified:{query}:{result.get('state')}")
        if not any(expected_title.casefold() in path.casefold() for path in paths):
            raise AssertionError(f"expected_title_missing:{query}:{paths}")
    packet = compose_multi_source_packet(
        "What is autism?",
        include_legacy_wikipedia=True,
        resolve_legacy_redirects=True,
        include_runtime=False,
    )
    if not packet.get("ok") or not (packet.get("legacy_wikipedia") or {}).get("ok"):
        raise AssertionError(f"typed_packet_not_verified:{packet.get('legacy_wikipedia')}")
    facts = (packet.get("packet") or {}).get("facts") or []
    if not any("wikipedia_local" in str(row.get("claim")) for row in facts):
        raise AssertionError("typed_packet_missing_local_wikipedia_fact")
    intent = build_intent_packet(
        query="What is autism?",
        knowledge_query="What is autism?",
        knowledge_mode="multi_source",
        include_legacy_wikipedia=True,
        resolve_legacy_redirects=True,
        mode="converse",
    )
    messages = packet_to_messages(intent)
    user_wire = "\n".join(
        str(row.get("content") or "")
        for row in messages
        if str(row.get("role") or "") == "user"
    )
    if contains_telemetry_disclosure(user_wire) or "internal_only" in user_wire.casefold():
        raise AssertionError("ordinary_model_packet_contains_internal_operational_label")
    if "autism" not in user_wire.casefold():
        raise AssertionError("ordinary_model_packet_missing_grounded_autism_context")
    print("PASS wikipedia legacy natural-language fallback regression")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
