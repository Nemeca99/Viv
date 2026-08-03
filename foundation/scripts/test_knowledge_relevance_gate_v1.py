"""Ensure live-memory priority cannot create unrelated knowledge hits."""
from __future__ import annotations

import sys
from unittest.mock import patch
from pathlib import Path

VIV = Path(__file__).resolve().parents[2]
FOUNDATION = VIV / "foundation"
for path in (VIV, FOUNDATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.aios_adapter_knowledge import query  # noqa: E402


def main() -> int:
    result = query("Autism spectrum", k=5)
    hits = result.get("hits") or []
    assert all(
        "autism" in str(hit.get("text") or "").casefold()
        or "spectrum" in str(hit.get("text") or "").casefold()
        for hit in hits
    ), hits
    assert not any(str(hit.get("source") or "").startswith("live:") for hit in hits), hits

    # The legacy fallback is allowed to serve unscoped evidence, but a
    # source-scoped CPU query must fail closed on missing or mismatched
    # provenance rather than widening into another source family.
    legacy_hits = [
        {"source": "legacy:unknown", "text": "requested fact", "score": 1},
        {
            "source": "legacy:dataset",
            "source_ref": {"root": "F_AI_DATASETS"},
            "text": "requested fact from dataset",
            "score": 1,
        },
    ]
    with patch("lib.aios_adapter_knowledge._load_index", return_value={"chunks": []}), patch(
        "lib.aios_knowledge.keyword_retrieve", return_value=legacy_hits
    ):
        scoped = query("requested fact", k=5, source_roots=("F_AI_DATASETS",))
    assert [hit.get("source") for hit in scoped.get("hits") or []] == ["legacy:dataset"], scoped

    with patch("lib.aios_adapter_knowledge._load_index", return_value={"chunks": []}), patch(
        "lib.aios_knowledge.keyword_retrieve", return_value=[legacy_hits[0]]
    ):
        unknown_scoped = query("requested fact", k=5, source_roots=("F_AI_DATASETS",))
    assert unknown_scoped.get("hits") == [], unknown_scoped
    print(f"KNOWLEDGE_RELEVANCE_GATE_PASS hits={len(hits)} live_unrelated_rejected=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
