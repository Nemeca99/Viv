"""Bounded read-only semantic-shard smoke test."""
from __future__ import annotations

import os
from pathlib import Path

from lib.knowledge_staged_adapter import query


SHARD = Path(__file__).resolve().parents[1] / "artifacts" / "auto" / "knowledge" / "wikipedia_semantic_shard_v1_20260803T114500Z.json"
CASES = (
    ("a classic arcade video game involving a spaceship and asteroids", "000128_Asteroids video game.txt", True),
    ("a county in Scotland", "000160_Aberdeenshire.txt", True),
    ("a chain of islands or island group", "000193_Archipelago.txt", True),
    ("the magnitude of a number without regard to its sign", "000224_Absolute value.txt", True),
    ("the economy and industries of Angola", "000096_Economy of Angola.txt", True),
)


def main() -> int:
    if os.environ.get("VIV_EMBED_BACKEND") != "hf_local":
        raise SystemExit("set VIV_EMBED_BACKEND=hf_local for this local semantic-shard test")
    if not SHARD.is_file():
        raise SystemExit("semantic_shard_missing")
    passed = 0
    for text, expected, should_match in CASES:
        result = query(text, artifact_path=SHARD, k=3, threshold=0.35)
        names = [str(row.get("doc") or "") for row in result.get("hits") or []]
        matched = expected in names
        if matched == should_match:
            passed += 1
        else:
            raise AssertionError(f"unexpected_semantic_result:{text}:{names}:expected={should_match}")
        if result.get("evidence", {}).get("vector_index_written") or result.get("evidence", {}).get("persistent_index_written"):
            raise AssertionError("semantic_shard_authority_open")
        if not result.get("evidence", {}).get("rejected"):
            pass
    print(f"PASS semantic shard cases={passed}/{len(CASES)} expected_hits={sum(1 for _, _, expected in CASES if expected)} authority_closed=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
