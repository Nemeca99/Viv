#!/usr/bin/env python3
"""Ensure external source selection is explicit for ambiguous knowledge queries."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from voice_core.intent_packet import build_intent_packet  # noqa: E402
from lib.knowledge_external_adapters import (  # noqa: E402
    compose_multi_source_packet,
    query_legacy_wikipedia,
)


def main() -> int:
    with patch("lib.knowledge_external_adapters.fetch_wikipedia_summary") as fetch:
        implicit = build_intent_packet(
            query="What is evolution?",
            mode="converse",
            knowledge_query="evolution",
            knowledge_mode="multi_source",
            memory_top=1,
        )
        assert not fetch.called, "implicit Wikipedia lookup must be disabled"
    packet = implicit["knowledge_packet"] or {}
    assert not any((row.get("source") or {}).get("root") == "WIKIPEDIA_REST" for row in packet.get("facts") or [])

    with patch(
        "lib.knowledge_external_adapters.fetch_wikipedia_summary",
        return_value={"ok": False, "state": "INCONCLUSIVE", "error": "test_transport"},
    ) as fetch:
        explicit = build_intent_packet(
            query="What is evolution?",
            mode="converse",
            knowledge_query="evolution",
            knowledge_mode="multi_source",
            wikipedia_title="Evolution",
            memory_top=1,
        )
        assert fetch.called
    assert explicit.get("wikipedia_title") == "Evolution"
    legacy = query_legacy_wikipedia("Anarchism", limit=1, max_chars=256)
    assert legacy.get("ok") and legacy.get("state") == "VERIFIED"
    assert (legacy["facts"][0]["source"] or {}).get("kind") == "wikipedia_local_article"
    redirect_raw = query_legacy_wikipedia("Autism spectrum", limit=1, max_chars=256)
    assert redirect_raw.get("ok") and "#REDIRECT" in redirect_raw["facts"][0]["value"]
    redirect_resolved = query_legacy_wikipedia(
        "Autism spectrum", limit=1, max_chars=256, resolve_redirects=True
    )
    resolution = redirect_resolved.get("redirect_resolution") or {}
    assert resolution.get("resolved") == 1 and resolution.get("aliases") == 1
    resolved_fact = redirect_resolved["facts"][0]
    assert "#REDIRECT" not in resolved_fact["value"]
    assert resolved_fact["source"]["path"].endswith("007631_Autism.txt")
    composed_redirect = compose_multi_source_packet(
        "Autism spectrum",
        include_legacy_wikipedia=True,
        resolve_legacy_redirects=True,
        include_runtime=False,
    )
    assert composed_redirect["packet"]["authority"] == "knowledge_multi_source_v1"
    assert any(
        row["source"]["kind"] == "wikipedia_local_article_resolved_redirect"
        for row in composed_redirect["packet"]["facts"]
    )
    assert "F_AI_DATASETS" in composed_redirect["packet"]["three_way"]["present_sources"]
    wired = build_intent_packet(
        query="What is anarchism?",
        mode="converse",
        knowledge_query="Anarchism",
        knowledge_mode="multi_source",
        include_legacy_wikipedia=True,
        memory_top=1,
    )
    assert wired.get("include_legacy_wikipedia") is True
    wired_facts = (wired.get("knowledge_packet") or {}).get("facts") or []
    assert any((row.get("source") or {}).get("kind") == "wikipedia_local_article" for row in wired_facts)
    wired_redirect = build_intent_packet(
        query="What is autism spectrum?",
        mode="converse",
        knowledge_query="Autism spectrum",
        knowledge_mode="multi_source",
        include_legacy_wikipedia=True,
        resolve_legacy_redirects=True,
        memory_top=1,
    )
    assert wired_redirect.get("resolve_legacy_redirects") is True
    wired_redirect_facts = (wired_redirect.get("knowledge_packet") or {}).get("facts") or []
    assert any(
        (row.get("source") or {}).get("kind") == "wikipedia_local_article_resolved_redirect"
        for row in wired_redirect_facts
    )
    print("EXTERNAL_SOURCE_SELECTION_PASS cases=8 legacy_wikipedia=verified_packet_wired_redirects=resolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
