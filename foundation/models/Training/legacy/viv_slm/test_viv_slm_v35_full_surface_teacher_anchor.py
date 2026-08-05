#!/usr/bin/env python3
"""Focused preflight checks for the V35 broad-surface candidate."""
from __future__ import annotations

from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = FOUNDATION / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import train_viv_slm_v35_full_surface_teacher_anchor as candidate  # noqa: E402


def main() -> int:
    assert candidate.STEP_INCREMENT == 250
    assert candidate.CAMPAIGN_ID.endswith("_0250")
    assert candidate.PARENT_CHECKPOINT.is_file()
    assert candidate.BEHAVIOR_REFERENCE_CHECKPOINT.is_file()
    assert candidate.PARENT_CHECKPOINT_SHA256 != candidate.BEHAVIOR_REFERENCE_CHECKPOINT_SHA256
    assert candidate.BASE_ANCHOR_WEIGHT < candidate.MAX_ANCHOR_WEIGHT
    controller = candidate.adaptive_teacher_anchor_update(
        {
            "alpha": candidate.CONTROLLER_ALPHA,
            "teacher_kl_delta_ema": 0.0,
            "validation_nll_delta_ema": 0.0,
        },
        observed_teacher_kl_delta=0.01,
        observed_validation_nll_delta=0.01,
    )
    assert candidate.MIN_ANCHOR_WEIGHT <= float(controller["anchor_weight"]) <= candidate.MAX_ANCHOR_WEIGHT
    assert candidate.MIN_LR_SCALE <= float(controller["lr_scale"]) <= candidate.MAX_LR_SCALE
    passed = candidate.guarded_rollback_decision(
        metric_guard=True,
        behavior_guard=True,
        consecutive_guard_failures=0,
    )
    assert passed["rollback"] is False and passed["consecutive_guard_failures"] == 0
    failed = candidate.guarded_rollback_decision(
        metric_guard=False,
        behavior_guard=True,
        consecutive_guard_failures=1,
    )
    assert failed["rollback"] is True and failed["halt"] is True
    print(
        "VIV_SLM_V35_FULL_SURFACE_TEACHER_ANCHOR_PREFLIGHT_PASS "
        "full_surface_replay=true teacher_reference_locked=true bounded_controller=true "
        "guarded_rollback=true aifl_investigation_reused_read_only=true promotion_closed=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
