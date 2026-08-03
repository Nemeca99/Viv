"""Regression tests for bounded CARMA CPU retrieval re-ranking."""
from __future__ import annotations

import tempfile
import importlib
from pathlib import Path

module = importlib.import_module("memory_core.retrieve")


def main() -> int:
    original = module.PROVENANCE_DIRS
    with tempfile.TemporaryDirectory(prefix="viv_carma_rank_") as temp:
        root = Path(temp)
        live = root / "live"
        dream = root / "dream"
        live.mkdir()
        dream.mkdir()
        (live / "current.txt").write_text(
            "[live][knowledge] thermal plant stability and coolant state\n"
            "[live][knowledge] CPU thermal plant status\n"
            "[live][identity] Viv is the CPU authority and GPU is the mouth\n",
            encoding="utf-8",
        )
        (dream / "current.txt").write_text(
            "[dream][knowledge] unrelated music theory and rhythm notes\n",
            encoding="utf-8",
        )
        module.PROVENANCE_DIRS = {"live": live, "dream": dream}
        try:
            hits = module.retrieve("CPU authority", top=2)
            assert hits and hits[0]["text"].startswith("[live][identity]")
            assert hits[0]["retrieval_mode"] == "cpu_cosine_provisional"
            assert hits[0]["retrieval_similarity"] > 0.0
            assert all("path" in row and "line_no" in row for row in hits)

            one = module.retrieve("CPU authority", top=1)
            assert len(one) == 1 and "retrieval_mode" in one[0]
        finally:
            module.PROVENANCE_DIRS = original
    print("CARMA_RETRIEVAL_RANKER_PASS cases=2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
