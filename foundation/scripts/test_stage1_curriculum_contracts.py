"""CPU construction contracts for the 360-pair Stage 1 curriculum."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.aifl_holdout_split import load_ban_sets  # noqa: E402
from lib.training_tree_contracts import DOMAINS, validate_contrast_item  # noqa: E402
from scripts import stage1_curriculum as stage1  # noqa: E402


def main() -> int:
    assert stage1.JUDGE_CONTRACT_VERSION == "stage1_judge_v5"
    if stage1.JUDGED.is_file():
        rows = stage1.read_jsonl(stage1.JUDGED)
    elif stage1.PENDING.is_file():
        rows = stage1.read_jsonl(stage1.PENDING)
    else:
        captured: list[dict[str, object]] = []
        original_jsonl = stage1.secure_write_jsonl
        original_json = stage1.secure_write_json
        try:
            stage1.secure_write_jsonl = lambda _path, material, **_kwargs: captured.extend(material)
            stage1.secure_write_json = lambda *_args, **_kwargs: {}
            result = stage1.build()
        finally:
            stage1.secure_write_jsonl = original_jsonl
            stage1.secure_write_json = original_json
        assert result.get("ok"), result
        rows = captured

    assert len(rows) == 360
    assert Counter(str(row["domain"]) for row in rows) == Counter(
        {domain: 60 for domain in DOMAINS}
    )
    assert Counter(str(row["split"]) for row in rows) == Counter(stage1.SPLIT_COUNTS)
    for row in rows:
        assert validate_contrast_item(row) == [], row["node_id"]
        assert len(set(row["positive_drafts"])) == 3
        assert len(set(row["negative_drafts"])) == 3
        assert row["sft_target"] == "chosen_only"

    assert not stage1.has_current_judge_decision(
        {"judge_agreement": True, "judge": {}}
    )
    assert not stage1.has_current_judge_decision(
        {
            "judge_agreement": True,
            "judge": {
                "contract_version": stage1.JUDGE_CONTRACT_VERSION,
                "semantic_sensor": "superseded_sensor",
            },
        }
    )
    assert stage1.has_current_judge_decision(
        {
            "judge_agreement": True,
            "judge": {
                "contract_version": stage1.JUDGE_CONTRACT_VERSION,
                "semantic_sensor": stage1.SENSOR_VERSION,
            },
        }
    )

    bans = load_ban_sets()
    for key, ban_key in (
        ("pair_hash", "pair"),
        ("ask_hash", "ask"),
        ("ask_cluster_hash", "cluster"),
    ):
        values = [str(row[key]) for row in rows]
        assert len(values) == len(set(values))
        assert not (set(values) & bans[ban_key])

    print(json.dumps({
        "ok": True,
        "rows": len(rows),
        "by_split": dict(Counter(str(row["split"]) for row in rows)),
        "by_domain": dict(Counter(str(row["domain"]) for row in rows)),
        "draft_pairs_checked": len(rows) * 3,
        "frozen_overlap": 0,
        "judge_contract_version": stage1.JUDGE_CONTRACT_VERSION,
        "superseded_decision_rejected": True,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
