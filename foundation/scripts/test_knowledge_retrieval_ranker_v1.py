#!/usr/bin/env python3
"""Contract tests for bounded CPU retrieval ranking."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.knowledge_retrieval_ranker import rank_candidates  # noqa: E402


def main() -> int:
    rows = [
        {"source": "a", "i": 0, "score": 1, "text": "cats sleep in warm places"},
        {"source": "b", "i": 0, "score": 1, "text": "cosine retrieval ranks matching cats and sleep"},
        {"source": "c", "i": 0, "score": 1, "text": "unrelated electrical measurement"},
    ]
    ranked, mode = rank_candidates("cats sleep", rows)
    assert mode == "tfidf_cpu_provisional"
    assert ranked[0]["source"] == "a"
    assert all("text" in row and "source" in row for row in ranked)
    assert all("retrieval_similarity" in row for row in ranked)

    one, fallback_mode = rank_candidates("anything", [{"source": "x", "score": 2, "text": "one"}])
    assert fallback_mode == "keyword_cpu" and one[0]["source"] == "x"
    print("KNOWLEDGE_RETRIEVAL_RANKER_PASS cases=2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
