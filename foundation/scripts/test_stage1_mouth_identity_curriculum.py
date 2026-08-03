"""CPU-only contracts for the Viv/AIOS mouth-and-identity curriculum."""
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

from scripts.stage1_mouth_identity_curriculum import (  # noqa: E402
    AUTHORITY,
    COMMON_ASKS,
    build_rows,
    source_contract,
    validate_rows,
)


def main() -> int:
    contract = source_contract()
    assert contract["contract"]["identity"] == "Viv_within_AIOS"
    assert contract["contract"]["gpu"] == "generate_viv_speech_only"
    assert (
        contract["contract"]["services"]
        == "automatic_not_gpu_wielded_tools"
    )
    assert contract["bootstrap_goal_pack_is_evaluation_only"] is True
    assert contract["authority"] == AUTHORITY

    rows = build_rows()
    report = validate_rows(rows)
    assert report["ok"], report["errors"]
    assert report["status"] == "curriculum_ready_for_cpu_judging"
    assert len(rows) == 96
    assert Counter(row["split"] for row in rows) == {
        "train": 64,
        "development": 16,
        "frozen": 8,
        "adversarial": 8,
    }
    assert Counter(row["domain"] for row in rows) == {
        domain: 12 for domain in COMMON_ASKS
    }
    assert report["old_stage1_exact_ask_overlap"] == 0
    assert report["goal_pack_exact_ask_overlap"] == 0
    assert report["holdout_hash_overlap"] == 0
    assert all(value == 12 for value in report["unique_chosen_by_domain"].values())
    assert all(row["admission_status"] == "HOLD" for row in rows)
    assert all(row["train_ready"] is False for row in rows)
    assert AUTHORITY["training_authorized"] is False
    assert AUTHORITY["cpu_semantic_judge_complete"] is False
    assert AUTHORITY["registry_frozen"] is False
    assert AUTHORITY["live_backend"] == "qwen_gguf"
    print(
        json.dumps(
            {
                "ok": True,
                "status": report["status"],
                "rows": len(rows),
                "domains": len(COMMON_ASKS),
                "splits": report["by_split"],
                "training_authorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
