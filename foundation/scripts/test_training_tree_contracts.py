"""CPU negative tests for the layered training-tree contracts."""
from __future__ import annotations

import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
from lib.aifl_holdout_split import load_ban_sets
from lib.training_tree_contracts import (
    DOMAINS,
    ROOT_INVARIANTS,
    STAGES,
    summarize_seed,
    validate_contrast_item,
    validate_tree,
)
from scripts.training_tree import security_source_hash

ROOT = FOUNDATION / "artifacts" / "auto" / "openaster_training_tree"


def main() -> int:
    tree = json.loads((ROOT / "tree_v2.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (ROOT / "seed_nodes_v2.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert validate_tree(tree) == []
    assert tuple(tree["root_invariants"]) == ROOT_INVARIANTS
    assert tuple(spec["stage_id"] for spec in tree["stages"]) == STAGES
    assert tuple(tree["domains"]) == DOMAINS
    summary = summarize_seed(rows)
    assert summary["ok"], summary["errors"]
    assert summary["rows"] == 96
    assert set(summary["by_stage"].values()) == {12}
    assert set(summary["by_domain"].values()) == {16}

    broken = dict(rows[0])
    broken["negative_drafts"] = broken["negative_drafts"][:2]
    assert "negative_drafts_exactly_three" in validate_contrast_item(broken)
    broken = dict(rows[0])
    broken["sft_target"] = "chosen_and_rejected"
    assert "rejected_may_be_sft_target" in validate_contrast_item(broken)
    broken = dict(rows[0])
    broken["text"] = broken["rejected"]
    assert "ambiguous_sft_field" in validate_contrast_item(broken)
    broken = dict(rows[-1])
    broken["ancestor_stages"] = []
    assert "ancestor_stages" in validate_contrast_item(broken)

    bans = load_ban_sets()
    assert not ({row["pair_hash"] for row in rows} & bans["pair"])
    assert not ({row["ask_hash"] for row in rows} & bans["ask"])
    assert not ({row["ask_cluster_hash"] for row in rows} & bans["cluster"])
    assert all(row["train_ready"] is False for row in rows)
    compact_source = security_source_hash({"pair_hash": "5bbb05aad92fae8a"})
    assert len(compact_source) == 64
    assert all(char in "0123456789abcdef" for char in compact_source)
    full_source = "a" * 64
    assert security_source_hash({"pair_hash": full_source}) == full_source
    print(json.dumps({
        "ok": True, "rows": 96, "stages": 8, "domains": 6,
        "negative_cases": 6, "frozen_overlap": 0,
        "security_source_hash": "sha256",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
