"""CPU-only contracts for the rejected 16-step bootstrap postmortem."""
from __future__ import annotations

import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts.stage1_generation_bootstrap_postmortem import (  # noqa: E402
    AUTHORITY,
    build_postmortem,
    render_markdown,
)


def main() -> int:
    report = build_postmortem()
    assert report["verdict"] == "stage1_generation_bootstrap_16_rejected"
    assert report["optimization"]["healthy"] is True
    assert report["optimization"]["chosen_response_nll_last"] < (
        report["optimization"]["chosen_response_nll_first"]
    )
    assert report["generation"]["goal_contract_passed"] == 0
    assert report["generation"]["goal_contract_total"] == 8
    assert report["generation"]["non_english_outputs"] >= 1
    assert report["generation"]["security_denials"] == 2
    assert report["curriculum_audit"]["rows"] == 360
    assert report["curriculum_audit"]["identity_rows"] == 60
    assert report["curriculum_audit"]["identity_unique_chosen_responses"] == 1
    for term in ("aios", "memory", "tool", "automatic", "work"):
        assert report["curriculum_audit"]["term_row_counts"][term] == 0
    assert report["root_cause"]["primary"] == "curriculum_scope_mismatch"
    assert report["next_action"] == "build_stage1_mouth_identity_curriculum_v1"
    assert report["authority"] == AUTHORITY
    assert AUTHORITY["rung_32_authorized"] is False
    assert AUTHORITY["full_80_step_lease_authorized"] is False
    assert AUTHORITY["bootstrap_rerun_authorized"] is False
    markdown = render_markdown(report)
    assert "curriculum_scope_mismatch" in markdown
    assert "32-step rung" in markdown
    print(
        json.dumps(
            {
                "ok": True,
                "verdict": report["verdict"],
                "optimization_healthy": report["optimization"]["healthy"],
                "goal_contract": "0/8",
                "identity_unique_chosen": 1,
                "next_action": report["next_action"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
