"""Verify v17 target diversity, semantic validity, and closed governance."""
from __future__ import annotations

import json
import re
import sys
from itertools import combinations
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
CAMPAIGN = ROOT / "campaigns/mouth_combined_candidate_v17"

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge
from voice_core.acronym_registry import validate_acronym_usage

CONTRACT_WORDS = set("adaptive intelligent operating system aios central processing unit cpu graphics processing unit gpu viv mouth model ai human human like service services memory memories logging logs speech voice reasoning decisions decision context rendering render operator tools tool evidence record records verified verification uncertain uncertainty claim claims".split())


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower())) - CONTRACT_WORDS


def main() -> int:
    manifest = json.loads((CAMPAIGN / "MANIFEST.json").read_text(encoding="utf-8"))
    rows = load(CAMPAIGN / "train_308_candidate_hold.jsonl")
    assert manifest["status"] == "COMBINED_CANDIDATE_HOLD_TRAINING_CLOSED"
    assert len(rows) == 308 and manifest["replacements"] == 23
    assert len({row["ask_hash"] for row in rows}) == 308
    assert len({row["target_hash"] for row in rows}) == 308
    assert all(not validate_acronym_usage(row["target"]) for row in rows)
    assert all(judge(row["target"], axis=row["axis"])["status"] == "PASS" for row in rows)
    assert all(row.get("sentence_count", 0) <= 3 and row.get("approx_token_count", 0) <= 45 for row in rows)
    near_pairs = 0
    normalized = [words(row["target"]) for row in rows]
    for i, j in combinations(range(len(rows)), 2):
        if rows[i]["axis"] != rows[j]["axis"]:
            continue
        union = normalized[i] | normalized[j]
        score = len(normalized[i] & normalized[j]) / len(union) if union else 1.0
        near_pairs += score >= 0.90
    assert near_pairs == 0
    assert all(row.get("training_authorized") is False and row.get("run_authorized") is False for row in rows[272:])
    print({"ok": True, "rows": 308, "replacements": 23, "unique_targets": 308,
           "near_copy_pairs_ge_0_90": 0, "all_targets_pass": True, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
