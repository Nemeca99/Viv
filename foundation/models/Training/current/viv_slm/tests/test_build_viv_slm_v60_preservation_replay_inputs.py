#!/usr/bin/env python3
"""Focused preparation test for the canonical V60 identity data contract."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_viv_slm_v60_preservation_replay_inputs as builder  # noqa: E402


def main() -> int:
    plan = builder.build_plan()
    assert plan["status"] == "DRY_RUN_READY"
    assert plan["authority"]["training_authorized"] is False
    assert plan["identity_index"]["identity_before_knowledge"] is True
    assert plan["identity_index"]["knowledge_admission"] is False
    assert plan["base"]["train_examples"] == 55106
    assert plan["base"]["validation_examples"] == 8696
    assert plan["retention"]["selected_train_examples"] == 5511
    assert plan["retention"]["validation_examples_excluded"] == 8672
    assert plan["output"]["train_examples"] == 60617
    assert plan["output"]["validation_source"].endswith("v43_conversation_focus")
    print("viv_slm_v60_preservation_replay_builder_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
