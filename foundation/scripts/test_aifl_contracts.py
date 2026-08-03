"""Regression tests for preference-row and semantic-class contracts."""
from __future__ import annotations

from lib.aifl_contracts import validate_preference_row, validate_semantic_class
from lib.viv_judge_train_gate import admit_pair


def main() -> int:
    row = {
        "at": "now", "ask": "x", "chosen": "y",
        "chosen_scores": {"vidi": 1, "intellexi": 1, "vixi": 1},
        "rejected": [], "n_drafts": 3, "min_drafts": 3,
        "alignment_required": True, "unanimous_alignment": True,
        "draft_mind_passes": 3, "source": "viv_shadow_judge",
    }
    assert validate_preference_row(row) == []
    assert admit_pair(row)["admit"] is True
    malformed = dict(row)
    malformed.pop("chosen_scores")
    assert "chosen_scores_not_object" in validate_preference_row(malformed)
    assert admit_pair(malformed)["reason"] == "invalid_preference_schema"
    assert validate_semantic_class("explain_vidi") == "explain_vidi"
    assert validate_semantic_class("judge_set") is None
    print({"ok": True, "valid_admit": True, "malformed_rejected": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
